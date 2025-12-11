# 스케줄링을 위한 모듈
from apscheduler.schedulers.background import BackgroundScheduler
import time
import queue
import concurrent.futures  # for 멀티스레딩
from datetime import datetime
from news_crawler import get_news_list, get_news  # 네이버 뉴스 크롤러
from enter_crawler import get_enter_list, get_enter  # 네이버 엔터 뉴스 크롤러
from sports_crawler import get_sports_list, get_sports  # 네이버 스포츠 뉴스 크롤러
from postprocess import analyze_news
from db import save_news, check_db_connection, check_elasticsearch_connection

news_queue = queue.Queue()
STOP_SIGNAL = "STOP"

# thread 수 지정
max_threads = 5

def fetch_news():
    """네이버 뉴스, 엔터 뉴스, 스포츠 뉴스 크롤링 후 큐에 추가"""
    print("[info] 뉴스 데이터 수집 시작...")


    news_sources = [
        ("네이버 뉴스", get_news_list, "news", 10),  # 최대 10페이지
        ("네이버 엔터 뉴스", get_enter_list, "enter", 4),  # 최대 4페이지
        ("네이버 스포츠 뉴스", get_sports_list, "sport", 4)  # 최대 4페이지
    ]



    total_news_count = 0
    seen_urls = set()  # 중복 확인을 위한 집합


    for source_name, list_func, news_type, max_pages in news_sources:
        start_page = 0 if news_type == "sport" else 1  # 스포츠 뉴스는 0부터 시작

        for page in range(start_page, max_pages + start_page):
            news_list = list_func(page)  # 해당 페이지의 뉴스 리스트 가져오기
            if not news_list:
                break  # 뉴스가 없으면 해당 소스 크롤링 종료

            for news in news_list:
                if news["naverUrl"] in seen_urls:  # 중복 뉴스 제거
                    continue

                seen_urls.add(news["naverUrl"])  # URL을 집합에 추가
                news_queue.put(news)  # 뉴스 큐에 추가
                total_news_count += 1

    print(f"\n[info] 총 {total_news_count}개 뉴스 큐에 추가 완료!\n")



def process_news():
    """Queue에서 뉴스 데이터를 가져와 하나씩 처리하는 Worker 스레드"""

    print("[info] thread 실행...")

    while True:
        news = news_queue.get()  # Queue에서 뉴스 가져오기 (Blocking)

        if news is STOP_SIGNAL:  # 종료 신호 확인
            print("[info] Worker 종료 신호 수신. 스레드 종료.")
            news_queue.task_done()
            break

        try:
            print(f"[info] 뉴스 처리 시작: {news['naverUrl']}")

            # 뉴스 타입별로 적절한 본문 크롤링 함수 호출
            if news["news_type"] == "news":
                news_data = get_news(news)
            elif news["news_type"] == "enter":
                news_data = get_enter(news)
            elif news["news_type"] == "sport":
                news_data = get_sports(news)
            else:
                print(f"[warn] 알 수 없는 뉴스 타입: {news['news_type']}")
                continue

            if not news_data:
                print(f"[error] 뉴스 크롤링 실패: {news['naverUrl']}")
                continue

            # 뉴스 분석
            analyzed_data = analyze_news(news_data)

            # 뉴스 저장
            save_news(analyzed_data)

            print(f"[info] 뉴스 처리 완료: {news['naverUrl']}")

        except Exception as e:
            print(f"[error] 뉴스 처리 실패: {news['naverUrl']} - {e}")
        finally:
            news_queue.task_done()  # 큐 작업 완료 처리

# 스케줄러 설정 (뉴스 수집 주기: 2분)
scheduler = BackgroundScheduler()

if __name__ == "__main__":
    print("[info] 뉴스 크롤러 시작!")

    check_db_connection()
    check_elasticsearch_connection()

    fetch_news()  # 딱 1번만 실행

    # 처리 스레드 실행
    executor = concurrent.futures.ThreadPoolExecutor(max_threads)
    for _ in range(max_threads):
        executor.submit(process_news)

    news_queue.join()
    executor.shutdown(wait=True)

