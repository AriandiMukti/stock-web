"""Create or serve an isolated, clearly labelled synthetic stock demo."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys

import pandas as pd

SYMBOLS = ('ADRO', 'BBRI', 'TLKM')
DEMO_VERSION = 1


def synthetic_summary(symbol, periods=80):
    """Deterministic illustration; no observations downloaded or copied."""
    index = SYMBOLS.index(symbol)
    days = pd.bdate_range(end='2026-11-16', periods=periods)
    base = (1000, 2000, 3000)[index]
    rows = []
    previous = base
    for i, day in enumerate(days):
        close = round(base*(1 + .001*(index+1)*i + .025*math.sin(i/7+index)), 2)
        opening = round(previous*(1 + .002*math.cos(i/5)), 2)
        volume = 1000000 + index*150000 + (i % 11)*35000
        net = round((80 + 25*math.sin(i/9+index)) * (1 if index != 1 else -.5), 2)
        rows.append({'Date':day.strftime('%d-%b-%y'), 'Open':opening,
            'High':round(max(opening,close)*1.012,2), 'Low':round(min(opening,close)*.988,2),
            'Close':close, 'Volume':volume, 'Value':round(volume*close,2),
            'Change':round((close/previous-1)*100,4), 'Avg Price':round((opening+close)/2,2),
            'Retail':-net*.75, 'Net Top3 All Lot':net*.8, 'Net Top5 All Lot':net,
            'Net Top10 All Lot':net*1.1, 'Total Buyer':12+index, 'Total Seller':10+index,
            'Synthetic':True})
        previous = close
    return pd.DataFrame(rows)


def _configure(root, secret):
    runtime = root/'var'
    os.environ['FLASK_RUNTIME_DIR'] = str(runtime)
    os.environ['BDM_BASE_PATH'] = str(runtime/'market-data')
    os.environ['DATABASE_URL'] = 'sqlite:///' + (runtime/'databases/demo.sqlite').as_posix()
    os.environ['SECRET_KEY'] = secret
    os.environ['DREAM_AGENT_WORKER_ENABLED'] = '0'
    os.environ['COOKIE_SECURE'] = '0'


def seed(root, email):
    root = root.expanduser().resolve()
    code = Path(__file__).resolve().parents[1]
    if root.exists() or root.is_relative_to(code) or code.is_relative_to(root):
        raise ValueError('Choose a new demo directory outside source code; existing directories are never overwritten')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(email)>150:
        raise ValueError('Invalid demo account email')
    if 'website.runtime_paths' in sys.modules:
        raise ValueError('Run the demo command in a fresh Python process')
    secret, password = secrets.token_urlsafe(48), secrets.token_urlsafe(18)
    _configure(root, secret)
    marker = root/'var/data/demo-provenance.json'
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({'synthetic':True, 'version':DEMO_VERSION,
        'symbols':SYMBOLS, 'sessions_per_symbol':80,
        'note':'All prices, broker-flow illustrations, positions and balances are synthetic.'},indent=2))
    frames = {}
    summary = root/'var/market-data/Daily/Summary'
    summary.mkdir(parents=True)
    for symbol in SYMBOLS:
        frame = synthetic_summary(symbol)
        frame.to_csv(summary/(symbol+'_Summary.csv'),index=False)
        frames[symbol] = frame
    from . import create_app, db
    from .models import User, PortfolioStocks, BestStocks, BestLowStocks, PatternUpStocks, Position, CashBalance, WatchlistHistory
    from werkzeug.security import generate_password_hash
    app = create_app()
    with app.app_context():
        user = User(email=email, firstName='Demo Sintetis', password=generate_password_hash(password))
        db.session.add(user); db.session.flush()
        for i, symbol in enumerate(SYMBOLS):
            frame = frames[symbol]; latest = frame.iloc[-1]
            values = dict(data=symbol,note='DEMO SINTETIS',diff5=0,retail=float(latest['Retail']),
                          avgPrice=float(latest['Close']),retailValue=0,userId=user.id)
            db.session.add(PortfolioStocks(**values))
            db.session.add((BestStocks,BestLowStocks,PatternUpStocks)[i](**values))
            db.session.add(Position(stock=symbol,buyPrice=float(frame.iloc[-15]['Close']),
                          lots=float((10,15,8)[i]),buyDate=pd.to_datetime(frame.iloc[-15]['Date'],format='%d-%b-%y').date(),userId=user.id))
            db.session.add(WatchlistHistory(stock=symbol,listType='PortfolioStocks',action='added',
                          avgPrice=float(latest['Close']),retailValue=0,userId=user.id))
        db.session.add(CashBalance(amount=25000000,userId=user.id))
        db.session.commit(); db.session.remove(); db.engine.dispose()
    config = root/'demo-config.json'
    config.write_text(json.dumps({'version':DEMO_VERSION,'synthetic':True,'secret_key':secret,'email':email},indent=2))
    login = root/'demo-login.txt'
    login.write_text('LOCAL SYNTHETIC DEMO ONLY\nEmail: '+email+'\nPassword: '+password+'\n',encoding='utf-8')
    for path in [config,login]:path.chmod(0o600)
    print(json.dumps({'synthetic':True,'stocks':list(SYMBOLS),'database_created':True,
                     'login_file':str(login),'root':str(root)}))


def serve(root, port):
    root = root.expanduser().resolve()
    config = json.loads((root/'demo-config.json').read_text())
    if config.get('synthetic') is not True or config.get('version') != DEMO_VERSION:
        raise ValueError('This is not a supported synthetic demo')
    if not (root/'var/databases/demo.sqlite').is_file() or not (root/'var/data/demo-provenance.json').is_file():
        raise ValueError('Demo database or provenance marker is missing')
    _configure(root, config['secret_key'])
    from . import create_app
    app = create_app()
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    create = sub.add_parser('seed'); create.add_argument('--out',type=Path,required=True)
    create.add_argument('--email',default='demo@example.invalid')
    start = sub.add_parser('serve'); start.add_argument('--root',type=Path,required=True)
    start.add_argument('--port',type=int,default=5087)
    args = parser.parse_args()
    if args.command=='seed':seed(args.out,args.email)
    else:serve(args.root,args.port)


if __name__=='__main__':main()
