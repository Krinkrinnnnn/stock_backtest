import pandas as pd
import os

def get_sp500_tickers(save_to_file=True):
    """
    從維基百科抓取最新的 S&P 500 成分股代碼，並轉換為 Yahoo Finance 兼容格式。
    """
    print("正在從維基百科獲取最新的 S&P 500 成分股清單...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    
    try:
        # 添加 headers 避免 403 Forbidden
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        table = pd.read_html(url, storage_options=headers)[0]
        tickers = table['Symbol'].tolist()
        
        # 清洗數據：Yahoo Finance 使用 '-' 而不是 '.' (例如 BRK.B -> BRK-B)
        tickers = [ticker.replace('.', '-') for ticker in tickers]
        
        if save_to_file:
            # 確保目錄存在
            os.makedirs('screen_result', exist_ok=True)
            file_path = 'screen_result/sp500_tickers.txt'
            with open(file_path, 'w') as f:
                for ticker in tickers:
                    f.write(f"{ticker}\n")
            print(f"成功獲取 {len(tickers)} 檔股票，已儲存至 {file_path}")
            
        return tickers
        
    except Exception as e:
        print(f"獲取 S&P 500 列表時發生錯誤: {e}")
        return []

# 測試執行
# sp500_list = get_sp500_tickers()