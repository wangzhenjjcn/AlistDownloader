import os
import json
import csv
import threading
import requests
import configparser
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

CONFIG_FILE = 'config.ini'
RESULTS_JSON = 'results.json'
RESULTS_TXT = 'results.txt'
RESULTS_CSV = 'results.csv'
DOWNLOAD_DIR = 'downloads'
LOCK = threading.Lock()

session = requests.Session()

# ------------------ 加载配置 ------------------
def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        print("未检测到 config.ini，正在创建...")
        url = input("请输入 Alist 分享站地址（如 https://pan.wwang.pw）：").strip()
        use_proxy = input("是否使用 SOCKS5 代理？(y/n)：").strip().lower() == 'y'
        proxy = input("请输入代理地址（如 127.0.0.1:1080）：").strip() if use_proxy else ''
        threads = input("请输入下载线程数（默认 10）：").strip()

        config['default'] = {
            'url': url,
            'use_proxy': str(use_proxy).lower(),
            'proxy': proxy,
            'threads': threads if threads.isdigit() else '10'
        }
        with open(CONFIG_FILE, 'w') as f:
            config.write(f)
    else:
        config.read(CONFIG_FILE)

    conf = config['default']
    if conf.getboolean('use_proxy') and conf['proxy']:
        session.proxies = {
            'http': f'socks5h://{conf["proxy"]}',
            'https': f'socks5h://{conf["proxy"]}'
        }
    return conf

# ------------------ 加载与保存进度 ------------------
def load_progress():
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_progress(data):
    with LOCK:
        with open(RESULTS_JSON, 'w', encoding='utf-8') as jf:
            json.dump(data, jf, ensure_ascii=False, indent=2)

        with open(RESULTS_TXT, 'w', encoding='utf-8') as tf:
            for path, url in data.items():
                tf.write(f"{path} -> {url}\n")

        with open(RESULTS_CSV, 'w', encoding='utf-8', newline='') as cf:
            writer = csv.writer(cf)
            writer.writerow(['path', 'url'])
            for path, url in data.items():
                writer.writerow([path, url])

# ------------------ 下载器 ------------------
def download_file(base_dir, url, path):
    local_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    if os.path.exists(local_path):
        print(f"[跳过] 已存在：{path}")
        return
    print(f"[开始下载] {path}")
    try:
        r = session.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"[完成下载] {path}")
    except Exception as e:
        print(f"[下载失败] {path} - {e}")

# ------------------ 获取下载地址 ------------------
def get_download_url(api_url, path):
    try:
        resp = session.post(urljoin(api_url, '/api/fs/get'), json={'path': path})
        resp.raise_for_status()
        return resp.json().get('data', {}).get('raw_url')
    except Exception as e:
        print(f"[获取失败] {path} - {e}")
        return None

# ------------------ 递归抓取 ------------------
def crawl(api_url, base_path, prefix, base_dir, progress, executor):
    try:
        resp = session.post(urljoin(api_url, '/api/fs/list'), json={'path': base_path})
        resp.raise_for_status()
        items = resp.json().get('data', {}).get('content', [])
    except Exception as e:
        print(f"[抓取失败] {base_path} - {e}")
        return
    
    if not items:
        return

    for item in items:
        full_path = os.path.join(base_path, item['name']).replace('\\', '/')
        relative_path = os.path.join(prefix, item['name']).replace('\\', '/')
        if item['type'] == 1:
            print(f"[目录] {relative_path}/")
            crawl(api_url, full_path, relative_path, base_dir, progress, executor)
        else:
            if relative_path in progress:
                print(f"[跳过] 已记录：{relative_path}")
                continue
            url = get_download_url(api_url, full_path)
            if url:
                progress[relative_path] = url
                save_progress(progress)
                executor.submit(download_file, base_dir, url, relative_path)

# ------------------ 主程序入口 ------------------
def main():
    conf = load_config()
    url = conf['url']
    thread_num = int(conf.get('threads', '10'))
    host = urlparse(url).netloc
    base_dir = os.path.join(DOWNLOAD_DIR, host)
    os.makedirs(base_dir, exist_ok=True)

    print("[INFO] 启动下载器...")
    progress = load_progress()
    with ThreadPoolExecutor(max_workers=thread_num) as executor:
        crawl(url, '/', '', base_dir, progress, executor)

if __name__ == '__main__':
    main()