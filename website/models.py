from . import db 
from flask_login import UserMixin
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declared_attr

stockList = [
    
             'AADI','AALI','ABBA','ABDA','ABMM','ACES','ACRO','ACST','ADCP','ADES','ADHI','ADMF','ADMG','ADMR','ADRO','AEGS',
                 'AGAR','AGII','AGRO','AGRS','AHAP','AIMS','AISA','AKKU','AKPI','AKRA','AKSI','ALDO','ALII','ALKA','ALMI','ALTO',
                 'AMAG','AMAN','AMAR','AMFG','AMIN','AMMN','AMMS','AMOR','AMRT','ANDI','ANJT','ANTM','APEX','APIC','APII','APLI',
                 'APLN','ARCI','AREA','ARGO','ARII','ARKA','ARKO','ARMY','ARNA','ARTA','ARTI','ARTO','ASBI','ASDM','ASGR','ASHA',
                 'ASII','ASJT','ASLC','ASLI','ASMI','ASPI','ASPR','ASRI','ASRM','ASSA','ATAP','ATIC','ATLA','AUTO','AVIA','AWAN',
                 'AXIO','AYAM','AYLS','BABP','BABY','BACA','BACH','BAIK','BAJA','BALI','BANK','BAPA','BAPI','BATA','BATR','BAUT',
                 'BAYU','BBCA','BBHI','BBKP','BBLD','BBMD','BBNI','BBRI','BBRM','BBSI','BBSS','BBTN','BBYB','BCAP','BCIC','BCIP',
                 'BDKR','BDMN','BEBS','BEEF','BEER','BEKS','BELI','BELL','BESS','BEST','BFIN','BGTG','BHAT','BHIT','BIKA','BIKE',
                 'BIMA','BINA','BINO','BIPI','BIPP','BIRD','BISI','BJBR','BJTM','BKDP','BKSL','BKSW','BLES','BLOG','BLTA','BLTZ',
                 'BLUE','BMAS','BMBL','BMHS','BMRI','BMSR','BMTR','BNBA','BNBR','BNGA','BNII','BNLI','BOAT','BOBA','BOGA','BOLA',
                 'BOLT','BOSS','BPFI','BPII','BPTR','BRAM','BREN','BRIS','BRMS','BRNA','BRPT','BRRC','BSBK','BSDE','BSIM','BSML',
                 'BSSR','BSWD','BTEK','BTEL','BTON','BTPN','BTPS','BUAH','BUDI','BUKA','BUKK','BULL','BUMI','BUVA','BVIC','BWPT',
                 'BYAN','CAKK','CAMP','CANI','CARE','CARS','CASA','CASH','CASS','CBDK','CBMF','CBPE','CBRE','CBUT','CCSI','CDIA',
                 'CEKA','CENT','CFIN','CGAS','CHEK','CHEM','CHIP','CINT','CITA','CITY','CLAY','CLEO','CLPI','CMNP','CMNT','CMPP',
                 'CMRY','CNKO','CNMA','COAL','COCO','COIN','COWL','CPIN','CPRI','CPRO','CRAB','CRSN','CSAP','CSIS','CSMI','CSRA',
                 'CTBN','CTRA','CTTH','CUAN','CYBR','DAAZ','DADA','DART','DATA','DAYA','DCII','DEAL','DEFI','DEPO','DEWA','DEWI',
                 'DFAM','DGIK','DGNS','DGWG','DIGI','DILD','DIVA','DKFT','DKHH','DLTA','DMAS','DMMX','DMND','DNAR','DNET','DOID',
                 'DOOH','DOSS','DPNS','DPUM','DRMA','DSFI','DSNG','DSSA','DUCK','DUTI','DVLA','DWGL','DYAN','EAST','ECII','EDGE',
                 'EKAD','ELIT','ELPI','ELSA','ELTY','EMAS','EMDE','EMMI','EMTK','ENAK','ENRG','ENVY','ENZO','EPAC','EPMT','ERAA',
                 'ERAL','ERTX','ESIP','ESSA','ESTA','ESTI','ETWA','EURO','EXCL','FAPA','FAST','FASW','FILM','FIMP','FIRE','FISH',
                 'FITT','FLMC','FMII','FOLK','FOOD','FORE','FORU','FPNI','FUJI','FUTR','FWCT','GAMA','GDST','GDYR','GEMA','GEMS',
                 'GGRM','GGRP','GHON','GIAA','GJTL','GLOB','GLVA','GMFI','GMTD','GOLD','GOLF','GOLL','GOOD','GOTO','GPRA','GPSO',
                 'GRIA','GRPH','GRPM','GSMF','GTBO','GTRA','GTSI','GULA','GUNA','GWSA','GZCO','HADE','HAIS','HAJJ','HALO','HATM',
                 'HBAT','HDFA','HDIT','HEAL','HELI','HERO','HEXA','HGII','HILL','HITS','HKMU','HMSP','HOKI','HOME','HOMI','HOPE',
                 'HOTL','HRME','HRTA','HRUM','HUMI','HYGN','IATA','IBFN','IBOS','IBST','ICBP','ICON','IDEA','IDPR','IFII','IFSH',
                 'IGAR','IIKP','IKAI','IKAN','IKBI','IKPM','IMAS','IMJS','IMPC','INAF','INAI','INCF','INCI','INCO','INDF','INDO',
                 'INDR','INDS','INDX','INDY','INET','INKP','INOV','INPC','INPP','INPS','INRU','INTA','INTD','INTP','IOTF','IPAC',
                 'IPCC','IPCM','IPOL','IPPE','IPTV','IRRA','IRSX','ISAP','ISAT','ISEA','ISSP','ITIC','ITMA','ITMG','JARR','JAST',
                 'JATI','JAWA','JAYA','JECC','JECX','JELI','JGLE','JIHD','JKON','JMAS','JPFA','JRPT','JSKY','JSMR','JSPT','JTPE',
                 'KAEF','KAQI','KARW','KAYU','KBAG','KBLI','KBLM','KBLV','KBRI','KDSI','KDTN','KEEN','KEJU','KETR','KIAS','KICI',
                 'KIJA','KING','KINO','KIOS','KJEN','KKES','KKGI','KLAS','KLBF','KLIN','KMDS','KMTR','KOBX','KOCI','KOIN','KOKA',
                 'KONI','KOPI','KOTA','KPIG','KRAS','KREN','KRYA','KSIX','KUAS','LABA','LABS','LAJU','LAND','LAPD','LCGP','LCKM',
                 'LEAD','LFLO','LIFE','LINK','LION','LIVE','LMAS','LMAX','LMPI','LMSH','LOPI','LPCK','LPGI','LPIN','LPKR','LPLI',
                 'LPPF','LPPS','LRNA','LSIP','LTLS','LUCK','LUCY','MABA','MAGP','MAHA','MAIN','MANG','MAPA','MAPB','MAPI','MARI',
                 'MARK','MASB','MAXI','MAYA','MBAP','MBMA','MBSS','MBTO','MCAS','MCOL','MCOR','MDIA','MDIY','MDKA','MDKI','MDLA',
                 'MDLN','MDRN','MEDC','MEDS','MEGA','MEJA','MENN','MERI','MERK','META','MFMI','MGLV','MGNA','MGRO','MHKI','MICE',
                 'MIDI','MIKA','MINA','MINE','MIRA','MITI','MKAP','MKNT','MKPI','MKTR','MLBI','MLIA','MLPL','MLPT','MMIX','MMLP',
                 'MNCN','MOLI','MORA','MPIX','MPMX','MPOW','MPPA','MPRO','MPXL','MRAT','MREI','MSIE','MSIN','MSJA','MSKY','MSTI',
                 'MTDL','MTEL','MTFN','MTLA','MTMH','MTPS','MTRA','MTSM','MTWI','MUTU','MYOH','MYOR','MYTX','NAIK','NANO','NASA',
                 'NASI','NATO','NAYZ','NCKL','NELY','NEST','NETV','NFCX','NICE','NICK','NICL','NIKL','NINE','NIRO','NISP','NOBU',
                 'NPGF','NRCA','NSSS','NTBK','NUSA','NZIA','OASA','OBAT','OBMD','OCAP','OILS','OKAS','OLIV','OMED','OMRE','OPMS',
                 'PACK','PADA','PADI','PALM','PAMG','PANI','PANR','PANS','PART','PBID','PBRX','PBSA','PCAR','PDES','PDPP','PEGE',
                 'PEHA','PEVE','PGAS','PGEO','PGJO','PGLI','PGUN','PICO','PIPA','PJAA','PJHB','PKPK','PLAN','PLAS','PLIN','PMJS',
                 'PMMP','PMUI','PNBN','PNBS','PNGO','PNIN','PNLF','PNSE','POLA','POLI','POLL','POLU','POLY','POOL','PORT','POSA',
                 'POWR','PPGL','PPRE','PPRI','PPRO','PRAY','PRDA','PRDL','PRIM','PSAB','PSAT','PSDN','PSGO','PSKT','PSSI','PTBA',
                 'PTDU','PTIS','PTMP','PTMR','PTPP','PTPS','PTPW','PTRO','PTSN','PTSP','PUDP','PURA','PURE','PURI','PWON','PYFA',
                 'PZZA','RAAM','RAFI','RAJA','RALS','RANC','RANS','RATU','RBMS','RCCC','RDTX','REAL','RELF','RELI','RGAS','RICY',
                 'RIGS','RIMO','RISE','RLCO','RMKE','RMKO','ROCK','RODA','RONY','ROTI','RSCH','RSGK','RUIS','RUNS','SAFE','SAGE',
                 'SAME','SAMF','SAPX','SATU','SBAT','SBMA','SCCO','SCMA','SCNP','SCPI','SDMU','SDPC','SDRA','SEMA','SFAN','SGER',
                 'SGRO','SHID','SHIP','SICO','SIDO','SILO','SIMA','SIMP','SINI','SIPD','SKBM','SKLT','SKRN','SKYB','SLIS','SMAR',
                 'SMBR','SMCB','SMDM','SMDR','SMGA','SMGR','SMIL','SMKL','SMKM','SMLE','SMMA','SMMT','SMRA','SMRU','SMSM','SNLK',
                 'SOCI','SOFA','SOHO','SOLA','SONA','SOSS','SOTS','SOUL','SPMA','SPRE','SPTO','SQMI','SRAJ','SRIL','SRSN','SRTG',
                 'SSIA','SSMS','SSTM','STAA','STAR','STRK','STTP','SUGI','SULI','SUNI','SUPA','SUPR','SURE','SURI','SWAT','SWID',
                 'TALF','TAMA','TAMU','TAPG','TARA','TAXI','TAYS','TBIG','TBLA','TBMS','TCID','TCPI','TDPM','TEBE','TECH','TELE',
                 'TFAS','TFCO','TGKA','TGRA','TGUK','TIFA','TINS','TIRA','TIRT','TKIM','TLDN','TLKM','TMAS','TMPO','TNCA','TOBA',
                 'TOOL','TOPS','TOSK','TOTL','TOTO','TOWR','TOYS','TPIA','TPMA','TRAM','TRGU','TRIL','TRIM','TRIN','TRIO','TRIS',
                 'TRJA','TRON','TRST','TRUE','TRUK','TRUS','TSPC','TUGU','TYRE','UANG','UCID','UDNG','UFOE','ULTJ','UNIC','UNIQ',
                 'UNIT','UNSP','UNTD','UNTR','UNVR','URBN','UVCR','VAST','VERN','VICI','VICO','VINS','VISI','VIVA','VKTR','VOKS',
                 'VRNA','VTNY','WAPO','WBSA','WEGE','WEHA','WGSH','WICO','WIDI','WIFI','WIIM','WIKA','WINE','WINR','WINS','WIRG',
                 'WMPP','WMUU','WOMF','WOOD','WOWS','WSBP','WSKT','WTON','YELO','YOII','YPAS','YULE','YUPI','ZATA','ZBRA','ZINC',
                 'ZONE','ZYRX'     



        ]    

class TypeDB():
    """
    Safe lookup for DB model classes by name.

    Previously this used eval(dbType), which let anyone pass arbitrary
    Python code via the `type` query/form param (e.g. ?type=...) and have
    it executed on the server. This whitelist approach only ever returns
    one of the known model classes below, or None if the name isn't
    recognized.
    """
    _REGISTRY = {}  # populated below, after the classes are defined

    @staticmethod
    def main(dbType):
        if not dbType:
            return None
        return TypeDB._REGISTRY.get(dbType)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    userId = db.Column(db.Integer, db.ForeignKey('user.id'))

class User(db.Model, UserMixin) :
    id = db.Column(db.Integer, primary_key = True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(512))
    firstName = db.Column(db.String(150))
    notes = db.relationship('Note')
    images = db.relationship('Images')
    portFolioStocks = db.relationship('PortfolioStocks')
    # increasingStocks = db.relationship('IncreasingStocks')
    # consistencyStocks = db.relationship('ConsistencyStocks')
    # lowerStocks = db.relationship('LowerStocks')
    # lowestStocks = db.relationship('LowestStocks')
    # diff5Stocks = db.relationship('Diff5Stocks')
    # diff5LowStocks = db.relationship('Diff5LowStocks')


class Images(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    data = db.Column(db.LargeBinary)
    userId = db.Column(db.Integer, db.ForeignKey('user.id'))

class Stocks():
    id = db.Column(db.Integer, primary_key = True)
    data = db.Column(db.String(50))
    note = db.Column(db.String(1000))
    diff5 = db.Column(db.Integer)
    retail = db.Column(db.Integer)
    avgPrice = db.Column(db.Integer)
    retailValue = db.Column(db.Integer)
    
    @declared_attr
    def userId(cls):
        return db.Column(db.Integer, db.ForeignKey('user.id'))

class PortfolioStocks(Stocks, db.Model):
    __tablename__ = 'PortfolioStocks'
	
class BestStocks(Stocks, db.Model):
    __tablename__ = 'BestStocks'

class BestLowStocks(Stocks, db.Model):
    __tablename__ = 'BestLowStocks'

class PatternUpStocks(Stocks, db.Model):
    __tablename__ = 'PatternUpStocks'

class PredictUpStocks(Stocks, db.Model):
    __tablename__ = 'PredictUpStocks'

class ContinueUpStocks(Stocks, db.Model):
    __tablename__ = 'ContinueUpStocks'

class PredContinueStocks(Stocks, db.Model):
    __tablename__ = 'PredContinueStocks'

class RetailSellStocks(Stocks, db.Model):
    __tablename__ = 'RetailSellStocks'

class RetailSellLowValueStocks(Stocks, db.Model):
    __tablename__ = 'RetailSellLowValueStocks'

class ConsolStocks(Stocks, db.Model):
    __tablename__ = 'ConsolStocks'

class ConsolLowValueStocks(Stocks, db.Model):
    __tablename__ = 'ConsolLowValueStocks'

class ReverseStocks(Stocks, db.Model):
    __tablename__ = 'ReverseStocks'


class WatchlistHistory(db.Model):
    """
    Log of add/remove events on the user-managed watchlists (Portfolio,
    Best, Best Low, Pattern Up), so a stock's past presence in a list —
    and the price/value it had at the time — isn't lost the moment it's
    removed.
    """
    id = db.Column(db.Integer, primary_key=True)
    stock = db.Column(db.String(10))
    listType = db.Column(db.String(50))
    action = db.Column(db.String(10))  # 'added' or 'removed'
    avgPrice = db.Column(db.Float)
    retailValue = db.Column(db.Float)
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    userId = db.Column(db.Integer, db.ForeignKey('user.id'))


class DecisionSnapshot(db.Model):
    """
    Snapshot of a ticker's decision-card inputs (skor pola, kesehatan
    arus, kandidat Kering) at one point in time, plus the price then --
    powers two things without needing new market-data sources:

    1. Jurnal Keputusan: reason='watchlist_add' rows, captured the moment
       a stock is added to Portfolio/Best/Best Low/Pattern Up (see
       admin() in utilities.py) -- "waktu itu Anda masuk saat kartu
       bilang apa, hasilnya sekarang berapa persen".
    2. Perubahan Sejak Kemarin: reason='daily' rows, one per ticker per
       hari kalender, captured opportunistically whenever Ringkasan
       Watchlist loads (see digest.py) -- membandingkan hari ini vs
       snapshot 'daily' terakhir untuk menemukan bendera yang berubah
       warna semalam.

    scannerJson/keringJson/flowJson menyimpan bentuk mentah yang SAMA
    persis dengan row.scanner/row.kering/row.flow di digest.py, supaya
    fungsi verdict JS yang sama (DecisionCard.scoreVerdict dkk di
    static/js/stock_chart.js) bisa dipakai ulang tanpa logika baru --
    NULL kalau dimensi itu tidak ada datanya saat snapshot diambil.
    """
    id = db.Column(db.Integer, primary_key=True)
    stock = db.Column(db.String(10))
    listType = db.Column(db.String(50))
    reason = db.Column(db.String(20))  # 'watchlist_add' or 'daily'
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    entryPrice = db.Column(db.Float)
    scannerJson = db.Column(db.Text)
    keringJson = db.Column(db.Text)
    flowJson = db.Column(db.Text)
    userId = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Position(db.Model):
    """
    An actual owned position (real money, real lots) — distinct from the
    watchlists above, which only track stocks being *monitored*, not
    stocks actually bought. Lets P&L be tracked against live price.

    KENAPA POSISI TERTUTUP TETAP TINGGAL DI TABEL INI
    Dulu menutup posisi berarti db.session.delete(): barisnya hilang, dan
    bersamanya satu-satunya catatan tentang apa yang benar-benar dibeli
    dengan uang sungguhan. Akibatnya app ini bisa mengukur pasar dari
    enam sudut (Scanner Lab, Screen Eval, Signal Recall, ...) tapi tidak
    pernah bisa menjawab "dari semua yang SAYA beli, hasilnya bagaimana".

    Sama seperti pola_jurnal.py: ini data yang hanya bisa didapat dengan
    mencatat, tidak bisa dikejar dengan menghitung ulang. Jadi posisi
    tertutup diberi sellPrice + sellDate dan TETAP di tabel; sellDate
    kosong berarti masih dipegang. Hapus permanen tetap ada, tapi untuk
    baris yang salah input, bukan untuk posisi yang selesai.
    """
    id = db.Column(db.Integer, primary_key=True)
    stock = db.Column(db.String(10))
    buyPrice = db.Column(db.Float)
    lots = db.Column(db.Float)  # 1 lot = 100 shares on IDX
    buyDate = db.Column(db.Date)
    sellPrice = db.Column(db.Float)   # None selama masih dipegang
    sellDate = db.Column(db.Date)     # None selama masih dipegang
    userId = db.Column(db.Integer, db.ForeignKey('user.id'))


class CashBalance(db.Model):
    """
    Dana nganggur (belum/tidak dibelikan saham) untuk halaman P&L --
    satu angka yang diinput manual, bukan dihitung dari histori
    transaksi. Position sudah mencatat apa yang dibeli, tapi tidak
    pernah tahu berapa cash yang masih tersisa di luar itu, jadi
    "Total Portfolio" (cash + nilai saham) tidak pernah bisa dihitung.

    Each user has a separate balance. Legacy unowned rows are retained
    but never automatically assigned to another account.
    """
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, default=0.0)
    userId = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=True)


# Whitelist of valid model names for TypeDB.main(). Anything not listed
# here is rejected (returns None) instead of being eval()'d.
TypeDB._REGISTRY = {
    'PortfolioStocks': PortfolioStocks,
    'BestStocks': BestStocks,
    'BestLowStocks': BestLowStocks,
    'PatternUpStocks': PatternUpStocks,
    'PredictUpStocks': PredictUpStocks,
    'ContinueUpStocks': ContinueUpStocks,
    'PredContinueStocks': PredContinueStocks,
    'RetailSellStocks': RetailSellStocks,
    'RetailSellLowValueStocks': RetailSellLowValueStocks,
    'ConsolStocks': ConsolStocks,
    'ConsolLowValueStocks': ConsolLowValueStocks,
    'ReverseStocks': ReverseStocks,
}


def scoped_query(model):
    """Scope personal lists to the authenticated account; market screens stay shared."""
    from flask import has_request_context
    from flask_login import current_user
    personal = {PortfolioStocks, BestStocks, BestLowStocks, PatternUpStocks,
                WatchlistHistory, Position, CashBalance, Note, Images, DecisionSnapshot}
    query = model.query
    if model not in personal:
        return query
    if not has_request_context() or not current_user.is_authenticated:
        return query.filter(False)
    return query.filter_by(userId=current_user.id)
