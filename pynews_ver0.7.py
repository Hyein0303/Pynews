
import streamlit as st
from bs4 import BeautifulSoup
import requests
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import pandas as pd
import urllib3
import openai
import os
from datetime import datetime

# 네이버 뉴스 크롤링 관련 함수와 변수
urllib3.disable_warnings()

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def filter_similar_articles(titles):
    if len(titles) == 0 or all(x.strip() == '' for x in titles):
        print("No valid articles to process.")
        return []

    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(titles)
    except ValueError:
        print("Could not fit TF-IDF due to empty vocabulary.")
        return []

    selected_titles = []
    selected_indices = []  # 유사한 기사를 필터링하기 위한 인덱스
    for index, title in enumerate(titles):
        is_similar = False
        for j in range(index+1, len(titles)):
            similarity = cosine_similarity(tfidf_matrix[index], tfidf_matrix[j])
            if similarity > 0.1:  # 임계값 설정 (이 값은 조절 가능)
                is_similar = True
                break
        if not is_similar:
            selected_titles.append(title)
            selected_indices.append(index)
    return selected_titles, selected_indices

def makePgNum(num):
    if num == 1:
        return num
    elif num == 0:
        return num + 1
    else:
        return num + 9*(num - 1)

def makeUrl(search, start_pg, end_pg, start_date, end_date):
    urls = []
    for i in range(start_pg, end_pg + 1):
        page = makePgNum(i)
        url = f"https://search.naver.com/search.naver?where=news&query={search}&sm=tab_opt&sort=0&photo=0&field=0&pd=3&ds={start_date}&de={end_date}&docid=&related=0&mynews=1&office_type=3&office_section_code=0&news_office_checked=&nso=so%3Ar%2Cp%3Afrom{start_date}to{end_date}&is_sug_officeid=0&office_category=3&service_area=0"
        urls.append(url)
    return urls


def news_attrs_crawler(articles, attrs):
    attrs_content = []
    for i in articles:
        attrs_content.append(i.attrs[attrs])
    return attrs_content

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/98.0.4758.102"}

def articles_crawler(url):
    original_html = requests.get(url, headers=headers, verify=False)
    html = BeautifulSoup(original_html.text, "html.parser")
    url_naver = html.select("div.group_news > ul.list_news > li div.news_area > div.news_info > div.info_group > a.info")
    urls = news_attrs_crawler(url_naver, 'href')
    return urls

# OpenAI GPT-3 요약 함수

def gpt_summarize(text):
    # 임의의 길이 제한으로 텍스트 블록 나누기
    word_blocks = [text.split()[i:i + 500] for i in range(0, len(text.split()), 500)]

    summarized_blocks = []
    for block in word_blocks:
        block_text = ' '.join(block)
        system_instruction = "assistant는 KT의 직원입니다. user의 입력된 글을 보고 업계 동향을 파악하기 위한 핵심만 3문장으로 요약해준다. 각 문장은 '✔️'로 시작하고, 개조식 문체를 이용한다. 마지막에는 모든 입력된 글에 대한 KT 직원으로서 알아야하는 점, 그리고 우리 회사가 앞으로 나아가야할 방향성과 전략 등 총평을 남긴다. 총평은 [GPT 총평]으로 시작한다.] "
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": block_text}]
        try:
            response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
            summarized_blocks.append(response['choices'][0]['message']['content'])
        except openai.error.OpenAIError as e:
            print(f"OpenAI API error: {e}")

    return ' '.join(summarized_blocks)  # 모든 블록의 요약을 합침

# 이메일 전송 함수
def send_email(naver_email,naver_password,subject, body, to_email):
    from_email = naver_email
    password = naver_password

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = ", ".join(to_email)
    msg["Subject"] = subject

    body_part = MIMEText(body, "html")
    msg.attach(body_part)
    
    for file in file_contents :
        part = MIMEApplication(file["content"], Name=file["name"])
        part["Content-Disposition"] = f'attachment; filename = "{file["name"]}"'
        msg.attach(part)

    smtp_server = "smtp.naver.com"
    smtp_port = 587
    try:
        smtp_conn = smtplib.SMTP(smtp_server, smtp_port)
        smtp_conn.starttls()
        smtp_conn.login(from_email, password)
        smtp_conn.sendmail(from_email, to_email, msg.as_string())
        print("이메일이 성공적으로 발송되었습니다.")
    except smtplib.SMTPException as e:
        print("이메일 발송 중 오류가 발생했습니다:", e)
    finally:
        smtp_conn.quit()


# 날짜 형식 변환 함수
def format_date(date_str):
    year, month, day = date_str.split(" ")[0].split("-")
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

def format_summarized_content(content):
    content = content.replace("✔️", "<br><br>✔️")
    content = content.replace("[GPT 총평]", "<br><br><br><strong style='font-size: 15px;'>[GPT 총평]</strong><br><br>")
    content += "<br><br><br>"  # 마지막에 두 줄 띄우기
    return content

# 현재 날짜와 시간을 얻기
now = datetime.now()

# 현재 월과 일을 얻기
current_month = now.month
current_day = now.day

# 해당 월의 첫 날짜를 찾기
first_day_of_month = datetime(now.year, current_month, 1)

# 월별 주차를 계산하기
current_week = ((now - first_day_of_month).days // 7) + 1


# Streamlit UI 설정
st.title("Let's 파이뉴스")

import asyncio

def get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return asyncio.get_event_loop()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# 사용자 입력을 받습니다.

openai_api_key = st.text_input("OpenAI API 키를 입력해주세요.", type="password")

search = st.text_input("검색할 키워드를 입력해주세요")
start_date = st.date_input("검색 시작 날짜를 입력해주세요")
end_date = st.date_input("검색 종료 날짜를 입력해주세요")
page = st.number_input("크롤링할 시작 페이지를 입력해주세요. ex)1(숫자만입력)", min_value=1)
page2 = st.number_input("크롤링할 종료 페이지를 입력해주세요. ex)1(숫자만입력)", min_value=1)
email_list = st.text_area("이메일 목록을 입력하세요 (쉼표로 구분)").split(',')
additional_text = st.text_area("파일 관련 설명을 적어주세요")
uploaded_files = st.file_uploader("여러 파일을 첨부하세요", type=["pdf", "jpg", "docx", "ppt", "pptx", "png"], accept_multiple_files = True)

file_contents = []
if uploaded_files :
    for uploaded_file in uploaded_files :
        file_details = {"FileName" : uploaded_file.name, "FileType" : uploaded_file.type, "FileSize" : uploaded_file.size}
        file_extension = file_details["FileName"].split(".")[-1]
        file_content = uploaded_file.read()
        file_contents.append({"content" : file_content, "name" : file_details["FileName"]}) 
        with open(f"{file_details['FileName']}", "wb") as f : f.write(file_content)

# OpenAI GPT-3 요약 함수
openai.api_key = openai_api_key


# "Run" 버튼이 눌렸을 때 실행됩니다.
if st.button("Run"):
    progress_bar = st.progress(0)

    # 기존의 코드를 적용합니다. 예를 들어,
    urls = makeUrl(search, page, page2, start_date.strftime('%Y.%m.%d'), end_date.strftime('%Y.%m.%d'))

    progress_bar.progress(0.2)
    
    news_url_1 = []

    for url in urls:
        url_list = articles_crawler(url)
        news_url_1.extend(url_list)

    final_urls = [url for url in news_url_1 if "news.naver.com" in url]
    news_dates, news_titles, news_contents, summarized_contents = [], [], [], []


    articles_data = []
    for url in final_urls:
        news = requests.get(url, headers=headers, verify=False)
        news_html = BeautifulSoup(news.text, "html.parser")

        title = news_html.select_one("#ct > div.media_end_head.go_trans > div.media_end_head_title > h2")
        if title is None:
            title = news_html.select_one("#content > div.end_ct > div > h2")

        content = news_html.select_one("article#dic_area")
        if content is None:
            content = news_html.select_one("div#articleBodyContents")
        if content is None:
            content = news_html.select_one("div.article_body_contents")
        if content is None:
            content = "Content not found"

        title = re.sub(pattern='<[^>]*>', repl='', string=str(title))
        content = re.sub(pattern='<[^>]*>', repl='', string=str(content))

        try:
            html_date = news_html.select_one("div#ct> div.media_end_head.go_trans > div.media_end_head_info.nv_notrans > div.media_end_head_info_datestamp > div > span")
            news_date = html_date.attrs['data-date-time']
        except AttributeError:
            news_date = news_html.select_one("#content > div.end_ct > div > div.article_info > span > em")
            news_date = re.sub(pattern='<[^>]*>', repl='', string=str(news_date))

        news_date = format_date(news_date)
        news_titles.append(title)
        news_contents.append(content)
        news_dates.append(news_date)

        articles_data.append({
            'date': news_date,
            'title': title,
            'content': content,
            'url': url
        })
    
    progress_bar.progress(0.4)
    
    # 기사 정보를 날짜 순서대로 정렬
    sorted_articles = sorted(articles_data, key=lambda x: x['date'], reverse=True)

    # 중복된 기사 제목 확인을 위한 집합(set) 생성
    unique_titles = set()
    
    # 중복된 기사를 제거한 결과를 저장할 리스트 생성
    filtered_sorted_articles = []

    for article in sorted_articles:
        title = article['title']
        # 기사 제목이 이미 unique_titles 집합에 있다면 중복된 기사로 간주하고 제외
        title = re.sub(r'[^\uAC00-\uD7A30-9a-zA-Z\s]', '', title)
            
        if title not in unique_titles:
            if title != '리벨리온 IBM과 생성형 AI 데이터센터 파트너십 구축':
                filtered_sorted_articles.append(article)
                unique_titles.add(title)

    # 중복된 기사가 제거된 결과를 sorted_articles 변수에 다시 할당
    sorted_articles = filtered_sorted_articles
    
    if not filtered_sorted_articles : 
        st.write("기사가 없습니다.")
    else : 
        # 기사 유사도 필터링
        news_titles, filtered_indices = filter_similar_articles(news_titles)
        temp = []
        for i in filtered_indices:
            temp.append(articles_data[i])

    progress_bar.progress(0.6)

    
    # HTML 이메일 본문 생성
    email_body = f"""
    <p style="font-family: Malgun Gothic;" >
        안녕하세요.
        <br>
        제안수행2본부의 탄력적 P-TF 파이뉴스 팀입니다.
        <br><br>
        본 메일은 Python을 이용하여 <b>특정 키워드 관련 기사를 크롤링</b>하고, 
        <span style="background-color: yellow; font-family: Malgun Gothic;">
            <b>ChatGPT가 내용을 요약해 자동으로 발송</b>
        </span>
        되었습니다. (금주 키워드 : {search.replace(' ', ', ')})
        <br>
        [GPT 총평]은 KT 업무 담당자의 입장에서 ChatGPT가 기사 내용의 Insight를 발굴하도록 설정되어 있습니다.
        <br>
        기사 제목에 링크를 첨부드리오니 상세 기사는 클릭 후 참고 부탁드립니다.
        <br>
        {additional_text}
  
        <br><br>
        감사합니다.
        <br>
        PYNEWS TF(신유현, 조혜진, 김도완, 김혜인, 배수빈, 이수영) 드림
    </p>
    """
    
    rows = []
    for article in sorted_articles:
        date = article['date']
        title = article['title']
        link = article['url']
        content = article['content']
        
        summarized_content = gpt_summarize(content)
        summarized_content = format_summarized_content(summarized_content)
        
        row_data = f"""
        <tr>
            <td style="text-align: center; font-family: Malgun Gothic;">{date}</td>
            <td style="vertical-align: middle; font-family: Malgun Gothic;"><a href="{link}">{title}</a></td>
            <td style="vertical-align: middle; font-family: Malgun Gothic;">{summarized_content}</td>
        </tr> 
        """
        rows.append(row_data)
    
    progress_bar.progress(0.8)
    
    table = f"""
    {email_body}
    <br><br>
    <table border="1" style="border-collapse: collapse; width: 100%;">
        <tr style="background-color: #9FD7F9; font-family: Malgun Gothic;">
            <th style="width: 10%;">날짜</th>
            <th style="width: 20%;">제목</th>
            <th style="width: 70%;">요약된 본문</th>
        </tr>
        {"".join(rows)}
    </table>
    """

    subject = f"[ChatGPT 자동요약] {current_month}월 {current_week}주차 ABC 트렌드 스크랩_키워드: {search.replace(' ', ', ')}"
    # 메인 실행 코드 부분에서 이메일 전송 부분
    # attachment_paths = ["Pynews/[테크&포커스] 황금알 AICC 잡아라… IT 인프라·통신기술 장전한 이통사.pdf"]
    # attachment_paths = []
    naver_email = "pynews@naver.com"
    naver_password = "pypypy!@#4"
    to_email_list = []
    to_email_list.extend(email_list)
    for to_email in to_email_list:
        send_email(naver_email,naver_password,subject, table, [to_email])
    progress_bar.progress(1.0)


    # 결과를 출력합니다.
    st.write("Crawled and summarized articles:")
    for article in sorted_articles:  # 예시: sorted_articles는 크롤링된 기사들
        st.write(f"Date: {article['date']}")
        st.write(f"Title: {article['title']}")
        st.write(f"Summary: {article['content']}")

