"""
Inference-only companion to deeplearning.py: loads the CNN it trains
(config.MODEL_PATH) and classifies a single ticker's most recent chart
window as bullish/bearish/sideways over the next PATTERN_FUTURE_DAYS days.

Training (generating thousands of labeled chart images, running epochs)
stays in deeplearning.py as a manual, standalone step. This module is
what utilities.py's /pattern-predict route calls on demand — it must
stay import-light-enough and fast enough (a few seconds) to run inside
a request.
"""
import io
import os

import numpy as np
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from PIL import Image

from .config import MODEL_PATH, PATTERN_LOOKBACK, PATTERN_FUTURE_DAYS

IMAGE_SIZE = (224, 224)

# image_dataset_from_directory (used in deeplearning.py:load_data) assigns
# class indices by sorting the label subfolder names alphabetically, not by
# the order they were created in — bearish/bullish/sideways, not
# bullish/bearish/sideways. Predictions must be decoded against this same
# order or the label mapping silently comes out wrong.
CLASS_NAMES = ['bearish', 'bullish', 'sideways']

_model = None


def _get_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"No trained model at {MODEL_PATH}. Run deeplearning.py first to train and save one."
            )
        import keras
        _model = keras.models.load_model(MODEL_PATH)
    return _model


def fetch_ohlc(ticker, lookback=PATTERN_LOOKBACK):
    """
    Downloads enough recent daily bars to build one lookback-window chart
    image, plus the SMA_20 the training images were annotated with (needs
    19 extra leading bars to warm up before the window we actually plot).
    """
    df = yf.download(ticker, period="2y", interval="1d", progress=False)
    if df.empty:
        return None

    # Same MultiIndex-flatten + numeric-coercion cleanup as
    # deeplearning.py:generate_and_label_data, so training and inference
    # see identically shaped data.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['SMA_20'] = df['Close'].rolling(20).mean()
    df = df.dropna()
    if len(df) < lookback:
        return None

    return df.tail(lookback)


def render_chart_image(chart_data, ticker):
    """Renders the same candle+volume+SMA20 chart as training, in memory."""
    fig, _ = mpf.plot(
        chart_data,
        type='candle',
        volume=True,
        figratio=(10, 8),
        figscale=1.2,
        style='yahoo',
        title=f'{ticker} {chart_data.index[-1].date()}',
        addplot=mpf.make_addplot(chart_data['SMA_20'], color='orange', panel=0),
        panel_ratios=(3, 1),
        returnfig=True,
    )
    buf = io.BytesIO()
    fig.savefig(buf, dpi=150, bbox_inches='tight')
    import matplotlib.pyplot as plt
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert('RGB')


def predict_pattern(ticker):
    """
    Returns {'label', 'probabilities', 'as_of', 'ohlc': <lookback dataframe>}
    for the given ticker, or None if there isn't enough price history.
    """
    model = _get_model()

    chart_data = fetch_ohlc(ticker)
    if chart_data is None:
        return None

    image = render_chart_image(chart_data, ticker)
    image = image.resize(IMAGE_SIZE)
    arr = np.asarray(image, dtype=np.float32) / 127.5 - 1.0
    arr = np.expand_dims(arr, axis=0)

    probs = model.predict(arr, verbose=0)[0]
    label = CLASS_NAMES[int(np.argmax(probs))]

    return {
        'label': label,
        'probabilities': {name: round(float(p), 4) for name, p in zip(CLASS_NAMES, probs)},
        'as_of': chart_data.index[-1].strftime('%Y-%m-%d'),
        'future_days': PATTERN_FUTURE_DAYS,
        'ohlc': chart_data,
    }
