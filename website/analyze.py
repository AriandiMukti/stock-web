try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
# %%


import pandas as pd
import os, math
import numpy as np
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor



from .models  import *
from . import db
from flask_login import current_user
from .config import BASE_PATH, DAILY_PATH, WEEKLY_PATH




import sys
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

def consol(df) :
    p_surge=4
    p_konsol=5
    total_kebutuhan_candle = p_surge + p_konsol

    df_surge = df.iloc[-total_kebutuhan_candle:-p_konsol]

    max_volume_index = df_surge["Volume"].idxmax()

    open1 = df_surge.loc[max_volume_index, "Open"]
    close1 = df_surge.loc[max_volume_index, "Close"]
    volume1 = df_surge.loc[max_volume_index, "Volume"]

    valueMax = round(
        ((open1 + close1) / 2 * volume1) / 1000000000, 2
    )
        
    df_konsol = df.iloc[-p_konsol:]

    ma20_volume = df["Volume"].rolling(20).mean().iloc[-p_konsol]
    volume_surge_tinggi = df_surge["Volume"].mean() > ma20_volume

    high_konsol = df_konsol[["Close", "Open"]].values.max()
    low_konsol = df_konsol[["Close", "Open"]].values.min()

    rentang_pct = (high_konsol - low_konsol) / low_konsol
    harga_sideways = rentang_pct <= 0.07

    volume_menurun = df_konsol["Volume"].mean() < (
        df_surge["Volume"].mean() * 0.75
    )

    df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
    ma_naik = (
        df["EMA10"].iloc[-1] > df["EMA10"].iloc[-p_konsol]
    )

    pola_terbentuk = (

        volume_surge_tinggi
        and harga_sideways
        and volume_menurun
        and ma_naik

    )
    return pola_terbentuk
    # if pola_terbentuk :
    #     testList.append((stock, f"{rentang_pct * 100:.2f}%"))

def process():
    
    external_tools = os.environ.get('EXTERNAL_TOOL_DIR')
    if external_tools:
        sys.path.append(os.path.abspath(external_tools))
    
    

    
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


    ################ HIGH VOL ###################
    VALUE_AVG_PARAM = 20
    VALUE_AVG_PARAM2 = 5

    def classify_stock(stock):
        """
        Worker for the parallel scan below: reads one stock's Daily +
        Weekly summary CSVs and classifies it into a screen (Consol /
        Retail Sell, at a 'high' or 'low' value tier). Returns None if
        the stock has no data file yet.

        Pulled out of the main loop so it can run in a thread pool —
        reading ~900 CSVs one at a time (mostly I/O wait) was the slow
        part of Analyze; threads let those reads overlap.
        """
        filePath = DAILY_PATH + 'Summary/' + stock + '_Summary.csv'
        filePath2 = WEEKLY_PATH + 'Summary/' + stock + '_Weekly_Summary.csv'

        if not os.path.exists(filePath):
            return None

        master = pd.read_csv(filePath)

        # Fresh listings / long-suspended stocks coming back (e.g. MKNT,
        # 1 row on 19 Oct 2026) don't have enough candles yet: change5
        # needs 5 and consol() needs 9 (4 surge + 5 consolidation).
        if len(master) < 9:
            return None

        master2 = pd.read_csv(filePath2)

        close1 = master['Close'].iloc[-1]
        open1 = master['Open'].iloc[-1]
        value1 = round(((open1 + close1) / 2 * master['Volume'].iloc[-1]) / 1000000000, 2)

        bdm5 = round(master2['Net Top3 All Lot'].iloc[-1] * 100, 2)
        bdm = round(master['Net Top5 All Lot'].iloc[-1] * 100, 2)
        diff5 = master['Net Top3 All Lot'].iloc[-1]
        change = round(master['Change'].iloc[-1], 2)

        if master['Close'].iloc[-5] >= master['Open'].iloc[-5]:
            change5 = round((master['Close'].iloc[-1] - master['Open'].iloc[-5]) / master['Open'].iloc[-5] * 100, 2)
        else:
            change5 = round((master['Close'].iloc[-1] - master['Close'].iloc[-5]) / master['Close'].iloc[-5] * 100, 2)

        retail = master['Retail'].iloc[-1]
        row = [stock, change, change5, bdm, bdm5, diff5, value1, retail]

        isConsol = consol(master)

        category = None
        if value1 >= VALUE_AVG_PARAM:
            if isConsol:
                category = 'consol'
            elif retail < 0:
                category = 'retailsell'
        elif VALUE_AVG_PARAM2 <= value1 < VALUE_AVG_PARAM:
            if isConsol:
                category = 'consol_low'
            elif retail < 0:
                category = 'retailsell_low'

        return {'category': category, 'row': row}

    with ThreadPoolExecutor(max_workers=16) as executor:
        scan_results = list(executor.map(classify_stock, stockList))

    ROW_COLUMNS = ['Stock', 'Change', 'Change5', 'BDM', 'BDM5', 'Diff5', 'Value', 'Retail']
    bucketed_rows = {'consol': [], 'retailsell': [], 'consol_low': [], 'retailsell_low': []}

    for result in scan_results:
        if result is None:
            continue
        if result['category']:
            bucketed_rows[result['category']].append(result['row'])


    dfConsol = pd.DataFrame(bucketed_rows['consol'], columns=ROW_COLUMNS)
    dfRetailSell = pd.DataFrame(bucketed_rows['retailsell'], columns=ROW_COLUMNS)
    dfConsolLowValue = pd.DataFrame(bucketed_rows['consol_low'], columns=ROW_COLUMNS)
    dfRetailSellLowValue = pd.DataFrame(bucketed_rows['retailsell_low'], columns=ROW_COLUMNS)

    for df in (dfConsol, dfRetailSell, dfConsolLowValue, dfRetailSellLowValue):
        if len(df) > 0:
            df.sort_values('Retail', ascending=[True], inplace=True)
            df.reset_index(drop=True, inplace=True)

    db.session.query(RetailSellStocks).delete()
    db.session.query(RetailSellLowValueStocks).delete()
    db.session.query(ConsolStocks).delete()
    db.session.query(ConsolLowValueStocks).delete()
    db.session.commit()

    def build_new_records(df, model_cls):
        """
        Turns a screened dataframe into ORM rows to insert, skipping any
        stock that's already tracked in another watchlist. Replaces four
        copy-pasted ~15-line loops that only differed in which dataframe/
        model class they used.
        """
        records = []
        for i in range(len(df)):
            row = df.iloc[[i]]
            stock = row["Stock"].iloc[0].upper()
            already_tracked = (
                scoped_query(PortfolioStocks).filter_by(data=stock).first()
                or scoped_query(BestStocks).filter_by(data=stock).first()
                or scoped_query(BestLowStocks).filter_by(data=stock).first()
                or scoped_query(PatternUpStocks).filter_by(data=stock).first()
            )
            if not already_tracked:
                records.append(model_cls(
                    data=stock,
                    note=str(row),
                    diff5=row["Diff5"].iloc[0],
                    retail=row["Retail"].iloc[0],
                    userId=current_user.id,
                ))
        return records

    newRecords = []
    newRecords += build_new_records(dfRetailSell, RetailSellStocks)
    newRecords += build_new_records(dfRetailSellLowValue, RetailSellLowValueStocks)
    newRecords += build_new_records(dfConsol, ConsolStocks)
    newRecords += build_new_records(dfConsolLowValue, ConsolLowValueStocks)

    def refresh_watchlist_metrics(records):
        """
        Refreshes retail/avgPrice/retailValue on existing watchlist rows
        from each stock's latest Daily Summary CSV. Replaces four
        copy-pasted loops (Portfolio/Best/Best Low/Pattern Up) that were
        otherwise identical.
        """
        for stock in records:
            filePath = DAILY_PATH + 'Summary/' + stock.data + '_Summary.csv'
            master = pd.read_csv(filePath)
            retail = master['Retail'].iloc[-1]
            avgPrice = master['Avg Price'].iloc[-1]
            stock.retail = retail
            stock.avgPrice = avgPrice
            stock.retailValue = retail * 100 * avgPrice / 1000000000

    refresh_watchlist_metrics(scoped_query(PortfolioStocks).all())
    refresh_watchlist_metrics(scoped_query(BestStocks).all())
    refresh_watchlist_metrics(scoped_query(BestLowStocks).all())
    refresh_watchlist_metrics(scoped_query(PatternUpStocks).all())

    try:
        db.session.add_all(newRecords)
        db.session.commit()
    except IntegrityError:
        logger.exception("process(): failed to commit new screen records")
        db.session.rollback()


def bdm_Current_Week(stock, typePath) :
    currentDays = datetime.today().isoweekday()
    # indexDays = 1
    todayFileFormat = datetime.today().strftime('%Y%m%d')
    if currentDays > 5 :
        offset = currentDays - 5
        currentDays = 5
        todayFileFormat = (datetime.today()- timedelta(days=offset)).strftime('%Y%m%d')

    
    broker= ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    foreignBroker = ['KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS']
    brokerYPPD = ['YP', 'PD']
    
    path = BASE_PATH + typePath + '\\Daily\\'
    col_names = ['Buyer', 'B Lot']
    col_names22 = ['Seller', 'S Lot']
    col_names2 = []
    col_names3 = ['Buyer', 'B Lot', 'Seller', 'S Lot']

    result = []
    result2 = []
    dataTable = []
    temp  = pd.DataFrame(dataTable, columns = col_names2)
    flagEmpty = ""
    df = pd.DataFrame(dataTable, columns = col_names3)
    resultTemp = []
    resultTemp2 = []
    temp  = pd.DataFrame(dataTable, columns = col_names2)
    for i in range(0, currentDays) :
        format =(datetime.strptime(todayFileFormat, '%Y%m%d') - timedelta(days=i)).strftime('%Y%m%d')
        if os.path.exists(path +  format + "\\" + stock + '-' + format + '.csv') :
            df = pd.read_csv(path + format + "\\" + stock + "-" + format + ".csv")
            df = df.replace(np.nan, '', regex=True)
            if i == 0 :
                temp[['Buyer', 'B Lot', 'Seller', 'S Lot']] = df[['Buyer', 'B Lot', 'Seller', 'S Lot']].to_numpy()
                temp = temp.replace(np.nan, '', regex=True)
            else :
                for k in range (df.shape[0]) :
                    if (not df['Buyer'][k] == flagEmpty) and ( df['Buyer'][k] in temp.values) :
                        if df['Buyer'][k] in temp['Buyer'].values :
                            dftemp = temp.loc[temp['Buyer'] == df['Buyer'][k]]
                            tempCount = dftemp['B Lot'] + df['B Lot'][k]
                            for i in range(len(result)):
                                if df['Buyer'][k] in str(result[i]['Buyer']) :
                                    result.pop(i)
                                    break
                            result.append({'Buyer' : df['Buyer'][k], 'B Lot' :int(tempCount.values)})
                            for i in range(len(result2)):
                                if df['Buyer'][k] in str(result2[i]['Seller']) :
                                    result2.pop(i)
                                    break

                        if df['Buyer'][k] in temp['Seller'].values :
                            dftemp = temp.loc[temp['Seller'] == df['Buyer'][k]]
                            tempCount = dftemp['S Lot'] + df['B Lot'][k]
                            
                            if tempCount.values >= 0 :

                                for i in range(len(result)):
                                    if df['Buyer'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                                result.append({'Buyer' : df['Buyer'][k], 'B Lot' :int(tempCount.values)})
                                for i in range(len(result2)):
                                    if df['Buyer'][k] in str(result2[i]['Seller']) :

                                        result2.pop(i)
                                        break
                            if tempCount.values < 0 :
                                for i in range(len(result2)):
                                    if df['Buyer'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break
                                result2.append({'Seller' : df['Buyer'][k], 'S Lot' :int(tempCount.values)})                                
                                for i in range(len(result)):
                                    if df['Buyer'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                            
                    if (not df['Seller'][k] == flagEmpty) and df['Seller'][k] in temp.values :
                        if df['Seller'][k] in temp['Seller'].values :
                            dftemp = temp.loc[temp['Seller'] == df['Seller'][k]]
                            tempCount = dftemp['S Lot'] + df['S Lot'][k]

                            for i in range(len(result2)):
                                if df['Seller'][k] in str(result2[i]['Seller']) :
                                    result2.pop(i)
                                    break
                            result2.append({'Seller' : df['Seller'][k], 'S Lot' :int(tempCount.values)})
                            for i in range(len(result)):
                                if df['Seller'][k] in str(result[i]['Buyer']) :
                                    result.pop(i)
                                    break

                        if df['Seller'][k] in temp['Buyer'].values :

                            dftemp = temp.loc[temp['Buyer'] == df['Seller'][k]]

                            tempCount = dftemp['B Lot'] + df['S Lot'][k]
                            if tempCount.values >= 0 :
                                for i in range(len(result)):
                                    if df['Seller'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                                result.append({'Buyer' : df['Seller'][k], 'B Lot' : int(tempCount.values)})
                                for i in range(len(result2)):
                                    if df['Seller'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break

                            if int(tempCount) < 0 :
                                for i in range(len(result2)):
                                    if df['Seller'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break
                                result2.append({'Seller' : df['Seller'][k], 'S Lot' : int(tempCount.values)})

                                for i in range(len(result)):
                                    if df['Seller'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break

                    if (not df['Buyer'][k] == flagEmpty) and (df['Buyer'][k] not in temp.values ):
                        for i in range(len(result)):
                            if df['Buyer'][k] in str(result[i]['Buyer']) :
                                result.pop(i)
                                break
                        result.append({'Buyer' : df['Buyer'][k], 'B Lot' :df['B Lot'][k]})

                    if (not df['Seller'][k] == flagEmpty) and (df['Seller'][k] not in temp.values) :
                        for i in range(len(result2)):

                            if df['Seller'][k] in str(result2[i]['Seller']) :
                                result2.pop(i)
                                break
                        result2.append({'Seller' : df['Seller'][k], 'S Lot' :df['S Lot'][k]})


                for x in range (temp.shape[0]) :
                    if (not temp['Buyer'][x] == flagEmpty) and (temp['Buyer'][x] not in df.values ):
                        for i in range(len(result)):
                            if temp['Buyer'][x] in str(result[i]['Buyer']) :
                                result.pop(i)
                                break
                        result.append({'Buyer' : temp['Buyer'][x], 'B Lot' :temp['B Lot'][x]})
                    if (not temp['Seller'][x] == flagEmpty) and (temp['Seller'][x] not in df.values ): 
                        for i in range(len(result2)):
                            if temp['Seller'][x] in str(result2[i]['Seller']) :
                                result2.pop(i)
                                break
                        result2.append({'Seller' : temp['Seller'][x], 'S Lot' :temp['S Lot'][x]})

                resultTemp  = pd.DataFrame(result, columns = col_names)
                resultTemp2  = pd.DataFrame(result2, columns = col_names22)
                resultTemp = resultTemp[resultTemp['B Lot'].notna()].sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
                resultTemp2 = resultTemp2[resultTemp2['S Lot'].notna()].sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)

                temp = pd.concat([resultTemp, resultTemp2],  axis=1)
                temp = temp.replace(np.nan, '', regex=True)
                
    result  = pd.DataFrame(resultTemp, columns = col_names)
    result2  = pd.DataFrame(resultTemp2, columns = col_names22)

    result = result[result['B Lot'].notna()].sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
    result2 = result2[result2['S Lot'].notna()].sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)
    if len(result) <= 1 :
        result[['Buyer', 'B Lot', 'Seller', 'S Lot']] = df[['Buyer', 'B Lot', 'Seller', 'S Lot']]
        resultFinal =  result
    else :
        resultFinal = pd.concat([result, result2], axis=1)

    result = []
    result2 = []

    finalList = []
    seller = []
    buyer = []
    for i in resultFinal['Seller'] :
        seller.append(str(i))

    
    for i in resultFinal['Buyer'] :
        buyer.append(str(i))

    # seller = seller[1:10].replace('nan', '')
    # buyer = buyer[1:10].replace('nan', '')
    
    buyer = [b for b in buyer if b!= 'nan']
    seller = [s for s in seller if s!= 'nan']

    buyer = buyer[0:10]
    seller = seller[0:10]
            # if buyer[b] == 'nan' :
            #     buyer.pop(b)

    # buyer = [b.remo('nan', '') for b in buyer]
    # seller = [s.replace('nan', '') for s in seller]

    counterBuyer = 0
    counterSeller = 0
    # if stock == 'TLKM' :
    for i in range(len(broker)) :
        if(broker[i] in buyer) :
            counterBuyer += 1
        if(broker[i] in seller) :
            counterSeller += 1
    
    counterBuyerYPPD = 0
    counterSellerYPPD = 0
    
    for i in range(len(brokerYPPD)) :
        if(brokerYPPD[i] in buyer) :
            counterBuyerYPPD += 1
        if(brokerYPPD[i] in seller) :
            counterSellerYPPD += 1


    testFlag = False
    if (counterBuyer >=3 and (counterBuyer > counterSeller)) or (counterBuyerYPPD == 2):
        finalList.append("BuyerYPPD")
        testFlag = True
    if ((counterSeller >=3 and (counterSeller > counterBuyer)) or (counterSellerYPPD ==2)) and not testFlag:
        finalList.append( "SellerYPPD")
        testFlag = True
    if not testFlag :
        finalList.append( "Netral")

    

    blist = []
    slist = []
    xx = 0
    for g in resultFinal['B Lot'] :
        if g != "" :
            if math.isnan(g) is False:
                blist.insert(xx, g)
                xx = xx + 1

    xx = 0    

    for gg in resultFinal['S Lot'] :
        if gg != "" :          
            if math.isnan(float(gg)) is False:
                slist.insert(xx, gg)
                xx = xx + 1

    if len(blist) < 10 :
        for t in range (len(blist), 10) :
            blist.insert(t, 0)

    if len(slist) < 10 :
        for t in range (len(slist), 10) :
            slist.insert(t, 0) 

    diff1 = blist[0] + slist[0]
    diff2 = blist[1] + slist[1] + diff1
    diff3 = blist[2] + slist[2] + diff2
    diff4 = blist[3] + slist[3] + diff3
    diff5 = blist[4] + slist[4] + diff4
    diff6 = blist[5] + slist[5] + diff5
    diff7 = blist[6] + slist[6] + diff6
    diff8 = blist[7] + slist[7] + diff7
    diff9 = blist[8] + slist[8] + diff8
    diff10 = blist[9] + slist[9] + diff9
    
    totalBlot = pd.to_numeric(resultFinal['B Lot'].head(5))
    totalSlot = pd.to_numeric(resultFinal['S Lot'].head(5))
    totalBlot = totalBlot.sum()
    totalSlot = totalSlot.sum()

    avg3 = diff3/totalBlot*100
    avg5 = diff5/totalBlot*100
    avg10 = (diff1 + diff2 + diff3 + diff4 + diff5 + diff6 + diff7 + diff8 + diff9 + diff10) /10/totalBlot*100
    avgTotal = (avg3 + avg5 + avg10)/3

    Btotal = blist[0] + blist[1]+ blist[2]+ blist[3]+ blist[4]+ blist[5]+ blist[6]+ blist[7]+ blist[8]+ blist[9]
    Stotal = slist[0] + slist[1]+ slist[2]+ slist[3]+ slist[4]+ slist[5]+ slist[6]+ slist[7]+ slist[8]+ slist[9]
    
    if diff10 < 0:
        lotTotal = (diff10 /Stotal)*(-1)
    else :
        if Btotal != 0 :
            lotTotal = diff10/Btotal
        else :
            lotTotal = 0

    Btotal5 = blist[0] + blist[1]+ blist[2]+ blist[3]+ blist[4]
    if diff5 >= 0 :
        if Btotal5 != 0 :
            diff5Lot = diff5 / totalBlot
        else :
            diff5Lot = 0
    else:
        diff5Lot = diff5 / (totalSlot) *-1
    
    diff5Lot = round(diff5Lot, 2)
    finalList.append(lotTotal)
    finalList.append(diff5Lot)
    finalList.append(diff5)

    resultFinal['B Lot'] = pd.to_numeric(resultFinal['B Lot'])
    test = resultFinal[resultFinal['B Lot'].notna()]
    test = test[test['B Lot'] > 99]
    
    resultFinal['S Lot'] = pd.to_numeric(resultFinal['S Lot'])
    test2 = resultFinal[resultFinal['S Lot'].notna()]
    test2 = test2[test2['S Lot'] < -99]
    
    isBuyerLessSeller = False

    if len(test2['S Lot']) > 0 and ( (len(test['B Lot']) / len(test2['S Lot'])) <= 0.5 ) :
        isBuyerLessSeller = True

    finalList.append(isBuyerLessSeller)    

    

    counterForeignBuyer = 0
    counterForeignSeller = 0
    for i in range(len(foreignBroker)) :
        if(foreignBroker[i] in buyer) :
            counterForeignBuyer += 1
        if(foreignBroker[i] in seller) :
            counterForeignSeller += 1
    
    foreignflag = False
    # if counterForeignBuyer >=3 and (counterForeignBuyer > counterForeignSeller) :
    if counterForeignBuyer >=3 :
        finalList.append("BuyerForeign")
        foreignflag = True
    # if (counterForeignSeller >=3 and (counterForeignSeller > counterForeignBuyer))  and not foreignflag:
    if (counterForeignSeller >=3)  and not foreignflag:
        finalList.append( "SellerForeign")
        foreignflag = True
    if not foreignflag :
        finalList.append( "NetralForeign")

    return finalList
    
def find_low(master, stock, dfStockLow, dfStockLowest, bdmCurrentWeek, change5, bdm5, diff5) :
    resultList = []

    master = master.tail(90)
    master = master.reset_index(drop=True)
    
    master['Lowest'] = "N"
    master['Lower'] = "N"
    lowest = master['Close'][0]
    highest = master['Close'][0]
    master.at[0, 'Lowest'] = 'Y'
    master['Higher'] = 'N'
    master['Highest'] = 'N'
    
    for i in range(len(master)) :
        if i > 1 :
            if (master['Close'][i] < master['Close'][i-1])  and master['Close'][i] < lowest:
                master.at[i, 'Lowest'] = 'Y'
                lowest = master['Close'][i]         
            if master['Change'][i] >=0 and (master['Close'][i] >= master['Close'][i-1]) and master['Change'][i-1] <=0 and (master['Close'][i-2] > master['Close'][i-1]) and master['Change'][i-2] <=0:
                master.at[i-1, 'Lower'] = 'Y'
            if (master['Close'][i] < master['Close'][i-1] or master['Close'][i] < master['Open'][i-1]) and (master['Close'][i-1] > master['Close'][i-2] or master['Open'][i-1] > master['Close'][i-2] ) :
                master.at[i-1, 'Higher'] = 'Y'
            if master['Higher'][i-1] == 'Y' and master['Higher'][i-2] == 'Y':
                master.at[i-2, 'Higher'] = 'N'
            if (master['Close'][i-1] > master['Close'][i] )  and master['Close'][i-1] > highest:
                master.at[i-1, 'Highest'] = 'Y'
                highest = master['Close'][i-1] 
            if (master['Open'][i-1] > master['Close'][i] )  and master['Open'][i-1] > highest:
                master.at[i-1, 'Highest'] = 'Y'
                highest = master['Open'][i-1] 

    dfLow = master.loc[master['Lower'] == 'Y']
    dfLowest = master.loc[master['Lowest'] == 'Y']
    dfHigh = master.loc[master['Higher'] == 'Y']

    if len(dfHigh) >= 1 and len(dfLow) >=2 and len(dfLowest) >= 1 :
        lastHighList = [dfHigh['Close'].iloc[-1]]

        lastLowIndexList = [dfLow.index[-1], dfLow.index[-2]]
        lastLowList = [dfLow['Close'].iloc[-1], dfLow['Close'].iloc[-2]]
        lastLowestIndex = dfLowest.index[-1]
        
        close = master['Close'].iloc[-1] 
        low = master['Low'].iloc[-1] 
        open =  master['Open'].iloc[-1] 
        change = round(master['Change'].iloc[-1] , 2)
        bdm = round(master['Lot'].iloc[-1] *100, 2) 
        value = round(((open+close)/2 * master['Volume'].iloc[-1]) / 1000000000, 2)
        diffHigher = (lastHighList[0] - close ) / close * 100 
        diffHighest = (highest - close ) / close * 100 
        vol = master['Volume'].iloc[-1] 
        volh1 = master['Volume'].iloc[-2] 
        isVolHigher = False
        isVolLower =  False

        if (change >= 0 and (vol > volh1)) or master['Doji'].iloc[-1] !=0 :
            isVolHigher = True
        if change < 0 and (vol < volh1) :
            isVolLower = True

        dftemp = pd.DataFrame([[stock, change, change5, bdm, bdmCurrentWeek, bdm5, diff5]], columns=['Stock', 'Change', 'Change5', 'BDM', 'CurrentBDM', 'BDM5', 'Diff5'])
        

        for j in range(len(lastLowList)) :
            diff = (close - lastLowList[j]) / close * 100
            difflow = (low - lastLowList[j]) / low * 100
            diffopen = (open - lastLowList[j]) / open * 100
            diff2 = (lastLowList[j] - close) / lastLowList[j] * 100
            if value >=4 and change5 <=6 and (diffHigher >= 5 or diffHighest >=7) and (isVolHigher or isVolLower):
                if close > lastLowList[j] or (diff2 <=2 and diff2 >= 0 and close < lastLowList[j]):
                    if (master['Date'].iloc[-1] != master['Date'][lastLowIndexList[j]]) :
                        dfStockLow = pd.concat([dfStockLow, dftemp])

        diffLowest = (close - dfLowest['Close'].iloc[-1]) / close * 100
        
        if diffLowest <= 5 :
            if (master['Date'].iloc[-1] != master['Date'][dfLowest.index[-1]]) :
                dfStockLowest = pd.concat([dfStockLowest, dftemp])
    
    resultList.append(dfStockLow)
    resultList.append(dfStockLowest)

    return resultList
    
def customBrokerSummary(pathList) :
    
    broker= ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    brokerYPPD = ['YP', 'PD']
    
    #path = '<market-data>/' + typePath + '\\Daily\\'
    import time
    start_time = time.time() 
    col_names = ['Buyer', 'B Lot']
    col_names22 = ['Seller', 'S Lot']
    col_names2 = []
    col_names3 = ['Buyer', 'B Lot', 'Seller', 'S Lot']

    result = []
    result2 = []
    dataTable = []
    temp  = pd.DataFrame(dataTable, columns = col_names2)
    flagEmpty = ""
    df = pd.DataFrame(dataTable, columns = col_names3)
    resultTemp = []
    resultTemp2 = []
    temp  = pd.DataFrame(dataTable, columns = col_names2)
    resultFinal =""
    for i in range(len(pathList)) :
        if os.path.exists(pathList[i]) :
            df = pd.read_csv(pathList[i])
            df = df.replace(np.nan, '', regex=True)
            if i == 0 :
                temp[['Buyer', 'B Lot', 'Seller', 'S Lot']] = df[['Buyer', 'B Lot', 'Seller', 'S Lot']].to_numpy()
                temp = temp.replace(np.nan, '', regex=True)
            else :
                for k in range (df.shape[0]) :
                    if (not df['Buyer'][k] == flagEmpty) and ( df['Buyer'][k] in temp.values) :
                        if df['Buyer'][k] in temp['Buyer'].values :
                            dftemp = temp.loc[temp['Buyer'] == df['Buyer'][k]]
                            tempCount = dftemp['B Lot'] + df['B Lot'][k]
                            for i in range(len(result)):
                                if df['Buyer'][k] in str(result[i]['Buyer']) :
                                    result.pop(i)
                                    break
                            result.append({'Buyer' : df['Buyer'][k], 'B Lot' :int(tempCount.values)})
                            for i in range(len(result2)):
                                if df['Buyer'][k] in str(result2[i]['Seller']) :
                                    result2.pop(i)
                                    break

                        if df['Buyer'][k] in temp['Seller'].values :
                            dftemp = temp.loc[temp['Seller'] == df['Buyer'][k]]
                            tempCount = dftemp['S Lot'] + df['B Lot'][k]
                            
                            if tempCount.values >= 0 :

                                for i in range(len(result)):
                                    if df['Buyer'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                                result.append({'Buyer' : df['Buyer'][k], 'B Lot' :int(tempCount.values)})
                                for i in range(len(result2)):
                                    if df['Buyer'][k] in str(result2[i]['Seller']) :

                                        result2.pop(i)
                                        break
                            if tempCount.values < 0 :
                                for i in range(len(result2)):
                                    if df['Buyer'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break
                                result2.append({'Seller' : df['Buyer'][k], 'S Lot' :int(tempCount.values)})                                
                                for i in range(len(result)):
                                    if df['Buyer'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                            
                    if (not df['Seller'][k] == flagEmpty) and df['Seller'][k] in temp.values :
                        if df['Seller'][k] in temp['Seller'].values :
                            dftemp = temp.loc[temp['Seller'] == df['Seller'][k]]
                            tempCount = dftemp['S Lot'] + df['S Lot'][k]

                            for i in range(len(result2)):
                                if df['Seller'][k] in str(result2[i]['Seller']) :
                                    result2.pop(i)
                                    break
                            result2.append({'Seller' : df['Seller'][k], 'S Lot' :int(tempCount.values)})
                            for i in range(len(result)):
                                if df['Seller'][k] in str(result[i]['Buyer']) :
                                    result.pop(i)
                                    break

                        if df['Seller'][k] in temp['Buyer'].values :

                            dftemp = temp.loc[temp['Buyer'] == df['Seller'][k]]

                            tempCount = dftemp['B Lot'] + df['S Lot'][k]
                            if tempCount.values >= 0 :
                                for i in range(len(result)):
                                    if df['Seller'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break
                                result.append({'Buyer' : df['Seller'][k], 'B Lot' : int(tempCount.values)})
                                for i in range(len(result2)):
                                    if df['Seller'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break

                            if int(tempCount) < 0 :
                                for i in range(len(result2)):
                                    if df['Seller'][k] in str(result2[i]['Seller']) :
                                        result2.pop(i)
                                        break
                                result2.append({'Seller' : df['Seller'][k], 'S Lot' : int(tempCount.values)})

                                for i in range(len(result)):
                                    if df['Seller'][k] in str(result[i]['Buyer']) :
                                        result.pop(i)
                                        break

                    if (not df['Buyer'][k] == flagEmpty) and (df['Buyer'][k] not in temp.values ):
                        for i in range(len(result)):
                            if df['Buyer'][k] in str(result[i]['Buyer']) :
                                result.pop(i)
                                break
                        result.append({'Buyer' : df['Buyer'][k], 'B Lot' :df['B Lot'][k]})

                    if (not df['Seller'][k] == flagEmpty) and (df['Seller'][k] not in temp.values) :
                        for i in range(len(result2)):

                            if df['Seller'][k] in str(result2[i]['Seller']) :
                                result2.pop(i)
                                break
                        result2.append({'Seller' : df['Seller'][k], 'S Lot' :df['S Lot'][k]})


                for x in range (temp.shape[0]) :
                    if (not temp['Buyer'][x] == flagEmpty) and (temp['Buyer'][x] not in df.values ):
                        for i in range(len(result)):
                            if temp['Buyer'][x] in str(result[i]['Buyer']) :
                                result.pop(i)
                                break
                        result.append({'Buyer' : temp['Buyer'][x], 'B Lot' :temp['B Lot'][x]})
                    if (not temp['Seller'][x] == flagEmpty) and (temp['Seller'][x] not in df.values ): 
                        for i in range(len(result2)):
                            if temp['Seller'][x] in str(result2[i]['Seller']) :
                                result2.pop(i)
                                break
                        result2.append({'Seller' : temp['Seller'][x], 'S Lot' :temp['S Lot'][x]})

                resultTemp  = pd.DataFrame(result, columns = col_names)
                resultTemp2  = pd.DataFrame(result2, columns = col_names22)
                resultTemp = resultTemp[resultTemp['B Lot'].notna()].sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
                resultTemp2 = resultTemp2[resultTemp2['S Lot'].notna()].sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)

                temp = pd.concat([resultTemp, resultTemp2],  axis=1)
                temp = temp.replace(np.nan, '', regex=True)
                
    result  = pd.DataFrame(resultTemp, columns = col_names)
    result2  = pd.DataFrame(resultTemp2, columns = col_names22)

    result = result[result['B Lot'].notna()].sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
    result2 = result2[result2['S Lot'].notna()].sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)
    if len(result) <= 1 :
        result[['Buyer', 'B Lot', 'Seller', 'S Lot']] = df[['Buyer', 'B Lot', 'Seller', 'S Lot']]
        resultFinal =  result
    else :
        resultFinal = pd.concat([result, result2], axis=1)
    logger.debug("customBrokerSummary timing: %.3fs", time.time() - start_time)
    resultFinal = resultFinal.replace(np.nan, '', regex=True)
    resultFinal = resultFinal.set_index('Buyer')

    pd.options.display.float_format = '{:,.0f}'.format

    
    
    resultFinal = resultFinal.to_html()
    
    resultFinal = resultFinal.replace('<thead>', '<!-- <thead>')
    resultFinal = resultFinal.replace('</thead>', '</thead> -->')
    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', '<table border="1" class="dataframe"> \n <thead> \n <tr style="text-align: right;"> \n <th>Buyer</th> \n <th>B Lot</th> \n <th>Seller</th> \n <th>S Lot</th> \n </thead>')


    #df.to_html('write_html.html', justify='center')
    style = "<style> tr { line-height: 40px; text-align: center;} \n th { text-align: center; line-height: 15px; color:grey; font-weight: bold; background-color: black; } \n td { width: 100px; color:grey; font-weight: bold; background-color: black; } \n .dataframe td:nth-child(2) { text-align: right; opacity: 0.8; color: rgb(150, 228, 61); font-weight: bold; } \n .dataframe td:nth-child(3) { text-align: center;} \n .dataframe td:nth-child(4) { text-align: right; opacity: 0.8;  color: rgb(246, 72, 72); font-weight: bold;} \n </style> \n"

    colgroup = '<colgroup> \n <col class="index" /> \n <col class="buyer"/> \n <col class="blot" /> \n <col class="seller"/> \n <col class="slot" style="color:red;"/> \n </colgroup>'

    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', style + '\n <table border="1" class="dataframe" id="dataframe"> \n' + colgroup)
    resultFinal = resultFinal.replace('<tr style="text-align: right;">', '<tr style="text-align: right; color:grey; font-weight: bold; background-color: black;">')
    resultFinal = resultFinal.replace('<col class="index" />', '')
    resultFinal = resultFinal.replace('<th></th>', '<th style="font-size: 0;">K</th>')

    foreignBroker = ['KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS']
    retailBroker= ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    for i in foreignBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    for i in retailBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    
    return resultFinal



def customBrokerSummary2(pathList) :
    
    pathNo = 0
    table = ''
    # Calculate avg price
    lotForAvg = 0
    for path in pathList :
        if os.path.exists(path) :
            if pathNo == 0 :
                table =  pd.read_csv(path)[['Buyer', 'B Lot', 'B Average', 'Seller', 'S Lot', 'S Average']]
            else :
            # table = pd.read_csv('<market-data>/LQ45\\Daily\\20220808\\TLKM-20220808.csv')
                table2 = pd.read_csv(path)

                
                tableBuyer = table['Buyer']
                tableBlot = table['B Lot']
                tableSeller = table['Seller']
                tableSlot = table['S Lot']
                tableAvgBuy = table['B Average']
                tableAvgSell = table['S Average']

                table2Buyer = table2['Buyer']
                table2Blot = table2['B Lot']
                table2Seller = table2['Seller']
                table2Slot = table2['S Lot']
                table2AvgBuy = table2['B Average']
                table2AvgSell = table2['S Average']

                
                
                # buyer buyer
                indexList = []
                indexList2 = []
                for index1 in range(len(tableBuyer)) :
                    if tableBuyer[index1] in table2Buyer.values :
                        index2 = table2.index[table2['Buyer'] == tableBuyer[index1]].values[0]
                        lot = tableBlot[index1] +  table2Blot[index2]
                        # tableBlot.loc[index1] = lot

                        # Calculate avg price
                        lotForAvg = lot
                        if lotForAvg == 0 :
                            tableAvgBuy.at[index1] = 0
                        else :
                            tableAvgBuy.at[index1] = round((tableBlot[index1] / lotForAvg * tableAvgBuy[index1]) + (table2Blot[index2] / lotForAvg * table2AvgBuy[index2]), 2)
                        

                        tableBlot.at[index1] = lot
                        indexList2.append(index2)

                        
                        
                # seller buyer
                for index1 in range(len(tableSeller)) :
                    if tableSeller[index1] in table2Buyer.values :
                        index2 = table2.index[table2['Buyer'] == tableSeller[index1]].values[0]
                        lot = tableSlot[index1]+  table2Blot[index2]

                        # Calculate avg price
                        lotForAvg = tableSlot[index1]*-1 +  table2Blot[index2]
                        if lot < 0 :
                            tableAvgSell.at[index1] = round((tableSlot[index1]*-1 / lotForAvg * tableAvgSell[index1]) + (table2Blot[index2] / lotForAvg * table2AvgBuy[index2]), 2)
                        else :
                            if lotForAvg == 0 :
                                tableAvgBuy.at[index1] = 0
                            else :
                                tableAvgBuy.at[index1] = round((tableSlot[index1]*-1 / lotForAvg * tableAvgSell[index1]) + (table2Blot[index2] / lotForAvg * table2AvgBuy[index2]), 2)
                        
                        
                        # Calculate avg price

                        if lot >=0 :
                            # table2Blot.loc[index2] = lot
                            table2Blot.at[index2] = lot
                            indexList.append(index1)
                        else :
                            # tableSlot.loc[index1] = lot
                            tableSlot.at[index1] = lot
                            indexList2.append(index2)

                        

                for i in indexList :
                    del tableSeller[i]
                    del tableSlot[i]
                    del tableAvgSell[i]

                for i in indexList2 :
                    del table2Buyer[i]
                    del table2Blot[i]
                    del table2AvgBuy[i]


                tableSeller = tableSeller.reset_index(drop=True)
                tableSlot = tableSlot.reset_index(drop=True)
                tableAvgSell = tableAvgSell.reset_index(drop=True)

                table2Buyer = table2Buyer.reset_index(drop=True)
                table2Blot = table2Blot.reset_index(drop=True)
                table2AvgBuy = table2AvgBuy.reset_index(drop=True)
                
                # # seller seller
                indexList = []
                indexList2 = []
                for index1 in range(len(tableSeller)) :
                    if tableSeller[index1] in table2Seller.values :
                        index2 = table2.index[table2['Seller'] == tableSeller[index1]].values[0]
                        lot = tableSlot[index1]+  table2Slot[index2]

                        # Calculate avg price
                        lotForAvg = lot
                        
                        if lotForAvg == 0 :
                            tableAvgSell.at[index1] = 0
                        else :
                            tableAvgSell.at[index1] = round((tableSlot[index1] / lotForAvg * tableAvgSell[index1]) + (table2Slot[index2] / lotForAvg * table2AvgSell[index2]), 2)
                        
                        # Calculate avg price


                        # tableSlot.loc[index1] = lot
                        tableSlot.at[index1] = lot
                        indexList2.append(index2)

                        
                # buyer seller
                for index1 in range(len(tableBuyer)) :
                    if tableBuyer[index1] in table2Seller.values :
                        index2 = table2.index[table2['Seller'] == tableBuyer[index1]].values[0]
                        lot = tableBlot[index1] + table2Slot[index2]

                        # Calculate avg price
                        lotForAvg = tableBlot[index1] + table2Slot[index2]*-1

                        if lot < 0 :
                            tableAvgSell.at[index1] = round((tableBlot[index1] / lotForAvg * tableAvgBuy[index1]) + (table2Slot[index2]*-1 / lotForAvg * table2AvgSell[index2]), 2)
                        else : 
                            if lotForAvg == 0 :
                                tableAvgBuy.at[index1] = 0
                            else :
                                tableAvgBuy.at[index1] = round((tableBlot[index1] / lotForAvg * tableAvgBuy[index1]) + (table2Slot[index2]*-1 / lotForAvg * table2AvgSell[index2]), 2)
                        
                        # Calculate avg price

                        if lot >=0 :
                            # tableBlot.loc[index1] = lot
                            tableBlot.at[index1] = lot
                            indexList2.append(index2)
                        else :
                            # table2Slot.loc[index2] = lot
                            table2Slot.at[index2] = lot
                            indexList.append(index1)


                for i in indexList :
                    del tableBuyer[i]
                    del tableBlot[i]
                    del tableAvgBuy[i]
                
                for i in indexList2 :
                    del table2Seller[i]
                    del table2Slot[i]
                    del table2AvgSell[i]
                
            
                tableBuyer  = pd.concat([tableBuyer, table2Buyer], ignore_index=True)
                tableSeller  = pd.concat([tableSeller, table2Seller], ignore_index = True)
                
                tableAvgBuy = pd.concat([tableAvgBuy, table2AvgBuy], ignore_index=True)
                tableAvgSell = pd.concat([tableAvgSell, table2AvgSell], ignore_index=True)

                tableBlot  = pd.concat([tableBlot, table2Blot], ignore_index = True)
                tableSlot  = pd.concat([tableSlot, table2Slot], ignore_index = True)
                
                buyer = pd.concat([tableBuyer, tableBlot, tableAvgBuy], axis=1).dropna().sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
                seller = pd.concat([tableSeller, tableSlot, tableAvgSell], axis=1).dropna().sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)
                
                table = pd.concat([buyer, seller], axis=1)
            pathNo += 1
    totalLot = table['B Lot'].sum()
    table = table.replace(np.nan, '', regex=True)

    avgPrice = 0
    for i in range(len(table['B Lot'])):
        if not isinstance(table['B Lot'][i], str) :
            avgPrice += table['B Lot'][i] / totalLot * table['B Average'][i]
    
    table.drop(columns=['B Average', 'S Average'], inplace=True)
    table['Avg Price'] = ''
    table.loc[0, 'Avg Price'] =  avgPrice

    # table['B Lot'] = table['B Lot'].apply(lambda x: f'{x:,.0f}' if not isinstance(x, str) else x)
    # table['S Lot'] = table['S Lot'].apply(lambda x: f'{x:,.0f}' if not isinstance(x, str) else x)

    # table['Avg Price'] = table['Avg Price'].apply(lambda x: f'{x:,.2f}' if not isinstance(x, str) else x)

    resultFinal = table
    
    resultFinal = resultFinal.replace(np.nan, '', regex=True)
    resultFinal = resultFinal.set_index('Buyer')

    # resultFinal = resultFinal.style.format({
    # 'B Lot': '{:,.0f}',  
    # 'S Lot': '{:,.0f}',  
    # 'Avg Price': '{:,.0f}'
    # })
    
    pd.options.display.float_format = '{:,.0f}'.format


    
    
    resultFinal = resultFinal.to_html()
    
    resultFinal = resultFinal.replace('<thead>', '<!-- <thead>')
    resultFinal = resultFinal.replace('</thead>', '</thead> -->')
    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', '<table border="1" class="dataframe"> \n <thead> \n <tr style="text-align: right;"> \n <th>Buyer</th> \n <th>B Lot</th> \n <th>Seller</th> \n <th>S Lot</th> \n <th>Avg</th> \n</thead>')


    #df.to_html('write_html.html', justify='center')
    style = "<style> tr { line-height: 40px; text-align: center;} \n th { text-align: center; line-height: 15px; color:grey; font-weight: bold; background-color: black; } \n td { width: 100px; color:grey; font-weight: bold; background-color: black; } \n .dataframe td:nth-child(2) { text-align: right; opacity: 0.8; color: rgb(150, 228, 61); font-weight: bold; } \n .dataframe td:nth-child(3) { text-align: center;} \n .dataframe td:nth-child(4) { text-align: right; opacity: 0.8;  color: rgb(246, 72, 72); font-weight: bold;}   \n .dataframe td:nth-child(5) { text-align: center; opacity: 0.8;  color: white; font-weight: bold; font-size:0.9em;} \n </style> \n"

    # colgroup = '<colgroup> \n <col class="index" /> \n <col class="buyer"/> \n <col class="blot" /> \n <col class="seller"/> \n <col class="slot" style="color:red;" \n <col class="avg" style="color:white;"/> \n </colgroup>'

    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', style + '\n <table border="1" class="dataframe" id="dataframe"> \n')
    resultFinal = resultFinal.replace('<tr style="text-align: right;">', '<tr style="text-align: right; color:grey; font-weight: bold; background-color: black;">')
    resultFinal = resultFinal.replace('<col class="index" />', '')
    resultFinal = resultFinal.replace('<th></th>', '<th style="font-size: 0;">K</th>')

    foreignBroker = ['KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS']
    retailBroker= ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    for i in foreignBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    for i in retailBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    
    return resultFinal


def customBrokerSummary3(pathList) :
    table = pd.DataFrame()
    
    for path in pathList :
        if os.path.exists(path) :
            table =  pd.concat([table, pd.read_csv(path)[['Buyer', 'B Lot', 'B Average', 'Seller', 'S Lot', 'S Average']]])
    if len(pathList) >= 2:
        tempTable = table[['Buyer', 'B Lot', 'B Average']].dropna().sort_values(['Buyer'], ascending=[True]).reset_index(drop=True)
        grouped1 = table.groupby('Buyer')['B Lot'].sum().reset_index()
        grouped1['B Average'] = 0

        tempBuyer = ''
        tempList = []
        for i in range(len(tempTable['Buyer'])):
            if isinstance(tempTable['Buyer'][i], str):

                if (tempBuyer != '') and (tempBuyer != tempTable['Buyer'][i]) :
                    index = grouped1.index[grouped1['Buyer'] == tempTable['Buyer'][i]].values[0] - 1
                    totalBlot = grouped1['B Lot'].iloc[index]
                    if totalBlot > 0:
                        grouped1['B Average'].at[index] = round(sum(x/totalBlot*y for x, y in tempList), 1)
                    tempList = []

                tempBuyer = tempTable['Buyer'][i]
                tempList.append((tempTable['B Lot'][i], tempTable['B Average'][i]))

        if (i == len(tempTable['Buyer'])-1) and tempBuyer != '':
            index = grouped1.index[grouped1['Buyer'] == tempBuyer].values[0]
            totalBLot = abs(grouped1['B Lot'].iloc[index])
            if totalBLot > 0:
                grouped1['B Average'].at[index] = round(sum(abs(x)/totalBLot*y for x, y in tempList), 1)

        tempTable = table[['Seller', 'S Lot', 'S Average']].dropna().sort_values(['Seller'], ascending=[True]).reset_index(drop=True)
        grouped2 = table.groupby('Seller')['S Lot'].sum().reset_index()
        grouped2['S Average'] = 0
        tempSeller = ''
        tempList = []
        for i in range(len(tempTable['Seller'])):
            if isinstance(tempTable['Seller'][i], str):

                if (tempSeller != '') and (tempSeller != tempTable['Seller'][i]) :
                    index = grouped2.index[grouped2['Seller'] == tempTable['Seller'][i]].values[0] - 1
                    totalSLot = abs(grouped2['S Lot'].iloc[index])
                    if totalSLot > 0:
                        grouped2['S Average'].at[index] = round(sum(abs(x)/totalSLot*y for x, y in tempList), 1)
                    tempList = []

                tempSeller = tempTable['Seller'][i]
                tempList.append((tempTable['S Lot'][i], tempTable['S Average'][i]))

        if (i == len(tempTable['Seller'])-1) and (tempSeller != ''):
            index = grouped2.index[grouped2['Seller'] == tempSeller].values[0]
            totalSLot = abs(grouped2['S Lot'].iloc[index])
            if totalSLot > 0:
                grouped2['S Average'].at[index] = round(sum(abs(x)/totalSLot*y for x, y in tempList), 1)

        indexList = []
        index2List = []
        for i in range(len(grouped1)):
            if grouped1['Buyer'].iloc[i] in grouped2['Seller'].values:
                
                index2 = grouped2.index[grouped2['Seller'] == grouped1['Buyer'].iloc[i]].values[0]
                lot = grouped1['B Lot'].iloc[i] + grouped2['S Lot'].iloc[index2]
                
                if lot >= 0 :
                    grouped1['B Lot'].at[i] = lot
                    index2List.append(index2)                
                else:
                    grouped2['S Lot'].at[index2] = lot
                    indexList.append(i)
                    
                    
        
        for index2 in index2List:
            grouped2 = grouped2.drop(index=index2)
        
        for i in indexList:
            grouped1 = grouped1.drop(index=i)

        grouped1 = grouped1.dropna().sort_values(['B Lot'], ascending=[False]).reset_index(drop=True)
        grouped2 = grouped2.dropna().sort_values(['S Lot'], ascending=[True]).reset_index(drop=True)

        table = pd.concat([grouped1, grouped2], axis=1)
    
    
    totalLot = table['B Lot'].sum()
    
    table = table.replace(np.nan, '', regex=True)

    avgPrice = 0
    for i in range(len(table['B Lot'])):
        if not isinstance(table['B Lot'][i], str) :
            avgPrice += table['B Lot'][i] / totalLot * round(table['B Average'][i], 1)

    # totalBuy5 = pd.to_numeric(table['B Lot'])[0:5].sum() * avgPrice / 10000000
    # totalSell5 = pd.to_numeric(table['S Lot'])[0:5].sum() * avgPrice / 10000000

    # totalBuy3 = pd.to_numeric(table['B Lot'])[0:3].sum() * avgPrice / 10000000
    # totalSell3 = pd.to_numeric(table['S Lot'])[0:3].sum() * avgPrice / 10000000

    # totalValue = totalBuy3 if totalBuy5 > abs(totalSell5) else totalSell3
    totalValue = (pd.to_numeric(table['B Lot'][0:5]).sum() + pd.to_numeric(table['S Lot'][0:5]).sum()) * avgPrice / 10000000

    table.drop(columns=['B Average', 'S Average'], inplace=True)
    table['Avg Price'] = ''
    table = table.applymap(lambda x: f"{x:.0f}" if isinstance(x, (int, float)) else x)
    table.loc[0, 'Avg Price'] =  f'{avgPrice:.1f}'


    table.loc[1, 'Avg Price'] =  f'{totalValue:.1f} B'

    resultFinal = table
    resultFinal = resultFinal.replace(np.nan, '', regex=True)
    resultFinal = resultFinal.set_index('Buyer')
    
    resultFinal = resultFinal.to_html()
    
    resultFinal = resultFinal.replace('<thead>', '<!-- <thead>')
    resultFinal = resultFinal.replace('</thead>', '</thead> -->')
    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', '<table border="1" class="dataframe"> \n <thead> \n <tr style="text-align: right;"> \n <th>Buyer</th> \n <th>B Lot</th> \n <th>Seller</th> \n <th>S Lot</th> \n <th>Average</th> \n</thead>')


    style = "<style> tr { line-height: 40px; text-align: center;} \n th { text-align: center; line-height: 15px; color:grey; font-weight: bold; background-color: black; } \n td { width: 100px; color:grey; font-weight: bold; background-color: black; } \n .dataframe td:nth-child(2) { text-align: right; opacity: 0.8; color: rgb(150, 228, 61); font-weight: bold; } \n .dataframe td:nth-child(3) { text-align: center;} \n .dataframe td:nth-child(4) { text-align: right; opacity: 0.8;  color: rgb(246, 72, 72); font-weight: bold;}   \n .dataframe td:nth-child(5) { text-align: center; opacity: 0.8;  color: white; font-weight: bold; font-size:0.9em;} \n </style> \n"

    resultFinal = resultFinal.replace('<table border="1" class="dataframe">', style + '\n <table border="1" class="dataframe" id="dataframe"> \n')
    resultFinal = resultFinal.replace('<tr style="text-align: right;">', '<tr style="text-align: right; color:grey; font-weight: bold; background-color: black;">')
    resultFinal = resultFinal.replace('<col class="index" />', '')
    resultFinal = resultFinal.replace('<th></th>', '<th style="font-size: 0;">K</th>')

    foreignBroker = ['KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS']
    # retailBroker = ['YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH']
    retailBroker = ['YP', 'PD', 'XL', 'XC']
    suspectBroker = ['MG']

    for i in foreignBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(246, 72, 72); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    for i in retailBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(150, 228, 61); font-weight: bold; opacity: 0.8;">'+i+'</th>')

    for i in suspectBroker:
        resultFinal = resultFinal.replace('<td>'+i+'</td>', '<td style="color: rgb(21, 38, 222); font-weight: bold; opacity: 0.8;">'+i+'</td>')
        resultFinal = resultFinal.replace('<th>'+i+'</th>', '<th style="color: rgb(21, 38, 222); font-weight: bold; opacity: 0.8;">'+i+'</th>')
    
    return resultFinal

def is_support(tempMaster, i):
    cond1 = (tempMaster['Low'][i] < tempMaster['Low'][i-1]) or (tempMaster['Close'][i] < tempMaster['Close'][i-1])
    cond2 = (tempMaster['Low'][i] < tempMaster['Low'][i+1]) or (tempMaster['Close'][i] < tempMaster['Close'][i+1])
    cond3 = (tempMaster['Low'][i+1] < tempMaster['Low'][i+2]) or (tempMaster['Close'][i+1] < tempMaster['Close'][i+2])
    cond4 = (tempMaster['Low'][i-1] < tempMaster['Low'][i-2]) or (tempMaster['Close'][i-1] < tempMaster['Close'][i-2])
    return (cond1 and cond2 and cond3 and cond4)

# determine bearish fractal
def is_resistance(table, i):
    cond1 = table['High'][i] > table['High'][i-1] 
    cond2 = table['High'][i] > table['High'][i+1]
    cond3 = table['High'][i+1] > table['High'][i+2]
    cond4 = table['High'][i-1] > table['High'][i-2]
    return (cond1 and cond2 and cond3 and cond4)
# %%
