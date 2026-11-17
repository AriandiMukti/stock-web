import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import yfinance as yf
import tensorflow as tf
import keras
from keras import layers, models, optimizers, callbacks, regularizers
# from tensorflow.keras import layers, models, optimizers, callbacks, regularizers
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight


import mplfinance as mpf

from config import MODEL_PATH, PATTERN_LOOKBACK, PATTERN_FUTURE_DAYS

# ======================================================
# 1. CONFIGURATION
# ======================================================
TICKERS = ["TPIA.JK"]  # Add more for better generalization
LOOKBACK = PATTERN_LOOKBACK    # days of past data for chart image
FUTURE_DAYS = PATTERN_FUTURE_DAYS  # days ahead to evaluate future return
THRESHOLD = 0.15       # 5% threshold (tune to 0.03 / 0.07 for comparison)
THRESHOLD_LOW = 0.1
IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 50
DATA_DIR = "stock_chart_data"
TEST_SPLIT = 0.1
VAL_SPLIT = 0.1

# ======================================================
# 2. DATA GENERATION & LABELING
# ======================================================
def generate_and_label_data(tickers, lookback=LOOKBACK, future_days=FUTURE_DAYS, threshold=THRESHOLD, threhold_low=THRESHOLD_LOW):
    """
    Generates labeled chart images for each ticker.
    Labels based on future return: >= threshold -> bullish, <= -threhold_low -> bearish, else sideways.
    """
    # Create directories
    for label in ['bullish', 'bearish', 'sideways']:
        os.makedirs(os.path.join(DATA_DIR, label), exist_ok=True)

    for ticker in tickers:
        print(f"\nProcessing {ticker}...")
        df = yf.download(ticker, start="2020-01-01", end="2025-12-31")  # 10 years for more data
        if df.empty:
            print(f"No data for {ticker}")
            continue

        # Flatten MultiIndex columns if they exist (yfinance can sometimes return these)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Ensure OHLCV columns are numeric, coercing errors to NaN
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate technical indicators for context
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['RSI'] = 100 - (100 / (1 + df['Close'].diff().clip(lower=0).rolling(14).mean() /
                                 -df['Close'].diff().clip(upper=0).rolling(14).mean()))
        df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
        df = df.dropna() # Drop rows with NaNs (including those created by to_numeric)

        total_images = 0
        for i in range(lookback, len(df) - future_days):
            # Compute label based on future returns
            past_price = df['Close'].iloc[i].item() # Ensure scalar
            future_price = df['Close'].iloc[i + future_days].item() # Ensure scalar
            future_return = (future_price - past_price) / past_price

            if future_return >= threshold:
                label = 'bullish'
            elif future_return <= -threhold_low:
                label = 'bearish'
            else:
                label = 'sideways'

            # Extract last lookback days of OHLCV
            chart_data = df.iloc[i - lookback:i]

            # Create and save chart image
            kwargs = dict(
                type='candle',
                volume=True,
                figratio=(10, 8),
                figscale=1.2,
                style='yahoo',
                title=f'{ticker} {df.index[i]}',
                addplot=mpf.make_addplot(chart_data['SMA_20'], color='orange', panel=0),
                panel_ratios=(3, 1)
            )
            file_name = os.path.join(DATA_DIR, label, f"{ticker}_{i}.png")
            mpf.plot(chart_data, savefig=dict(fname=file_name, dpi=150, bbox_inches='tight'), **kwargs)
            plt.close()
            total_images += 1

        print(f"Generated {total_images} images for {ticker}")

# ======================================================
# 3. DATA LOADING & PREPROCESSING
# ======================================================
def load_data(data_dir, img_size=IMAGE_SIZE, batch_size=BATCH_SIZE):
    dataset = tf.keras.utils.image_dataset_from_directory(
        data_dir,
        validation_split=VAL_SPLIT + TEST_SPLIT,
        subset="both",
        seed=42,
        image_size=img_size,
        batch_size=batch_size
    )
    train_ds = dataset[0]
    val_test_ds = dataset[1]

    # Split validation and test
    val_test_size = int(len(val_test_ds) * (VAL_SPLIT / (VAL_SPLIT + TEST_SPLIT)))
    val_ds = val_test_ds.take(val_test_size)
    test_ds = val_test_ds.skip(val_test_size)

    # Data augmentation for training only
    # data_augmentation = models.Sequential([
    #     layers.RandomFlip("horizontal"),
    #     layers.RandomRotation(0.1),
    #     layers.RandomZoom(0.1),
    #     layers.RandomWidth(0.1),
    #     layers.RandomHeight(0.1),
    # ])

    data_augmentation = models.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.1),
    layers.RandomZoom(0.1),
    # Replaces RandomHeight(0.1) and RandomWidth(0.1)
    layers.RandomTranslation(height_factor=0.1, width_factor=0.1) 
    ])

    # Normalize pixel values to [-1, 1]
    def normalize(img, label):
        img = tf.cast(img, tf.float32) / 127.5 - 1.0
        return img, label

    train_ds = train_ds.map(lambda x, y: (data_augmentation(x, training=True), y))
    train_ds = train_ds.map(normalize).prefetch(tf.data.AUTOTUNE)
    val_ds = val_ds.map(normalize).prefetch(tf.data.AUTOTUNE)
    test_ds = test_ds.map(normalize).prefetch(tf.data.AUTOTUNE)

    class_names = dataset[0].class_names
    print(f"Classes: {class_names}")
    return train_ds, val_ds, test_ds, class_names

# ======================================================
# 4. MODEL ARCHITECTURE (Fine-Tuned CNN)
# ======================================================
def build_model(input_shape=IMAGE_SIZE + (3,), num_classes=3):
    model = models.Sequential([
        layers.Input(shape=input_shape),

        # Block 1
        layers.Conv2D(32, (3, 3), padding='same', kernel_regularizer=regularizers.l2(0.00025)),
        layers.BatchNormalization(),
        layers.ReLU(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.2),

        # Block 2
        layers.Conv2D(64, (3, 3), padding='same', kernel_regularizer=regularizers.l2(0.00025)),
        layers.BatchNormalization(),
        layers.ReLU(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.2),

        # Block 3
        layers.Conv2D(128, (3, 3), padding='same', kernel_regularizer=regularizers.l2(0.00025)),
        layers.BatchNormalization(),
        layers.ReLU(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.3),

        # Block 4
        layers.Conv2D(256, (3, 3), padding='same', kernel_regularizer=regularizers.l2(0.00025)),
        layers.BatchNormalization(),
        layers.ReLU(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.3),

        # Block 5
        layers.Conv2D(512, (3, 3), padding='same', kernel_regularizer=regularizers.l2(0.00025)),
        layers.BatchNormalization(),
        layers.ReLU(),
        layers.GlobalAveragePooling2D(),

        # Classifier head
        layers.Dense(128, kernel_regularizer=regularizers.l2(0.00025)),
        layers.Dropout(0.5),
        layers.Dense(num_classes, activation='softmax')
    ])

    model.compile(
        optimizer=optimizers.Adam(learning_rate=0.0001),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=False),
        metrics=['accuracy']
    )
    return model

def compute_class_weights(data_dir, class_names):
    """
    Counts images per label folder and returns a {class_index: weight}
    dict ('balanced' scheme: rarer classes get higher weight) so
    model.fit() penalizes misclassifying bearish/bullish as heavily as
    the far more common sideways class, instead of the model minimizing
    loss by just always predicting the majority class.
    """
    labels = []
    for idx, name in enumerate(class_names):
        count = len([
            f for f in os.listdir(os.path.join(data_dir, name))
            if os.path.isfile(os.path.join(data_dir, name, f))
        ])
        labels.extend([idx] * count)

    weights = compute_class_weight('balanced', classes=np.arange(len(class_names)), y=np.array(labels))
    class_weight = {idx: float(w) for idx, w in enumerate(weights)}
    print(f"Class weights ({dict(zip(class_names, [class_weight[i] for i in range(len(class_names))]))})")
    return class_weight

# ======================================================
# 5. TRAINING WITH CALLBACKS
# ======================================================
def train_model(model, train_ds, val_ds, epochs=EPOCHS, class_weight=None):
    my_callbacks  = [
        callbacks.EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True),
        callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, min_lr=1e-6, verbose=1),
        callbacks.ModelCheckpoint(MODEL_PATH, save_best_only=True),
        callbacks.TensorBoard(log_dir="./logs")
    ]

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
        callbacks=my_callbacks,
        class_weight=class_weight,
    )
    return history

# ======================================================
# 6. EVALUATION & OVERFITTING DIAGNOSTICS
# ======================================================
def plot_training_history(history):
    """Plot training vs validation accuracy and loss to detect overfitting."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 4))

    axes[0].plot(history.history['accuracy'], label='Train Acc')
    axes[0].plot(history.history['val_accuracy'], label='Val Acc')
    axes[0].set_title('Model Accuracy')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Accuracy')
    axes[0].legend()

    axes[1].plot(history.history['loss'], label='Train Loss')
    axes[1].plot(history.history['val_loss'], label='Val Loss')
    axes[1].set_title('Model Loss')
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('Loss')
    axes[1].legend()

    plt.tight_layout()
    plt.show()

def evaluate_model(model, test_ds, class_names):
    """Compute classification report and confusion matrix on test set."""
    y_true = []
    y_pred = []

    for images, labels in test_ds:
        preds = model.predict(images, verbose=0)
        y_true.extend(labels.numpy())
        y_pred.extend(np.argmax(preds, axis=1))

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, target_names=class_names))

    print("Confusion Matrix:")
    cm = confusion_matrix(y_true, y_pred)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=class_names, yticklabels=class_names)
    plt.title('Test Confusion Matrix')
    plt.xlabel('Predicted')
    plt.ylabel('True')
    plt.show()

# ======================================================
# 7. MAIN EXECUTION
# ======================================================
if __name__ == "__main__":
    # Step 1: Generate data (comment out if data already exists)
    # print("Generating chart data...")
    # generate_and_label_data(TICKERS, LOOKBACK, FUTURE_DAYS, THRESHOLD, THRESHOLD_LOW)

    # Step 2: Load data
    print("\nLoading data...")
    train_ds, val_ds, test_ds, class_names = load_data(DATA_DIR)

    # Step 3: Build model
    print("\nBuilding model...")
    model = build_model(num_classes=len(class_names))
    model.summary()

    # Step 4: Train
    print("\nComputing class weights...")
    class_weight = compute_class_weights(DATA_DIR, class_names)

    print("\nTraining...")
    history = train_model(model, train_ds, val_ds, class_weight=class_weight)

    # Step 5: Evaluate
    print("\nEvaluating on test set...")
    evaluate_model(model, test_ds, class_names)

    # Step 6: Overfitting diagnostics
    print("\nPlotting training history...")
    plot_training_history(history)