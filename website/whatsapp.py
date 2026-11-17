"""Optional local GUI messaging tool. Importing this module never sends a message."""
import argparse
import os
from pathlib import Path
import re
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', required=True, type=int)
    args = parser.parse_args()
    recipient = os.environ['WHATSAPP_RECIPIENT']
    image_root = Path(os.environ['WHATSAPP_IMAGE_DIR']).expanduser().resolve()
    from . import create_app
    from .models import BestStocks
    import pywhatkit as kit
    app = create_app()
    with app.app_context():
        for record in BestStocks.query.filter_by(userId=args.user_id).all():
            code = str(record.data or '').upper()
            if not re.fullmatch(r'[A-Z0-9]{1,6}', code):
                continue
            image = image_root / (code + '.jpg')
            if image.is_file():
                kit.sendwhats_image(receiver=recipient, img_path=str(image), caption=code)
                time.sleep(2)


if __name__ == '__main__':
    main()
