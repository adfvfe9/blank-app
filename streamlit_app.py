import streamlit as st
from datetime import datetime
import pytz
import json
import random
import hashlib
import sqlite3

# --------------------------------------------------------------------------------
# 초기 설정 및 데이터베이스/단어 파일 연동
# --------------------------------------------------------------------------------

# 단어 목록 로드 (kword.txt)
@st.cache_resource
def load_words():
    """kword.txt 파일에서 단어 목록을 불러와 set으로 반환합니다."""
    try:
        with open("kword.txt", "r", encoding="utf-8") as f:
            words = {line.strip() for line in f if len(line.strip()) >= 2}
        return words
    except FileNotFoundError:
        st.error("kword.txt 파일을 찾을 수 없습니다. 프로젝트 루트에 파일을 추가해주세요.")
        # 파일이 없을 경우를 대비한 임시 단어 목록
        return {"스트림릿", "파이썬", "데이터", "게임", "단어", "목록", "인공지능"}

word_set = load_words()

# SQLite 데이터베이스 연결 및 초기화
conn = sqlite3.connect('kkutu_local.db', check_same_thread=False)
c = conn.cursor()

def init_db():
    # 사용자 정보 테이블
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            points INTEGER DEFAULT 0
        )
    ''')
    # 게임 상태 테이블 (항상 1개의 행만 존재)
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            start_char TEXT,
            last_update_hour INTEGER,
            word_history TEXT,
            last_word TEXT
        )
    ''')
    # 게임 상태 초기화 (만약 비어있다면)
    c.execute("SELECT count(*) FROM game_state WHERE id = 1")
    if c.fetchone()[0] == 0:
        initial_state = {
            'start_char': '가',
            'last_update_hour': datetime.now(pytz.timezone('Asia/Seoul')).hour,
            'word_history': json.dumps(['시작']),
            'last_word': '시작'
        }
        c.execute('''
            INSERT INTO game_state (id, start_char, last_update_hour, word_history, last_word)
            VALUES (1, ?, ?, ?, ?)
        ''', (initial_state['start_char'], initial_state['last_update_hour'], initial_state['word_history'], initial_state['last_word']))
    conn.commit()

# --------------------------------------------------------------------------------
# 세션 상태(Session State) 초기화
# --------------------------------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

# --------------------------------------------------------------------------------
# 유틸리티 함수 (두음법칙 포함)
# --------------------------------------------------------------------------------
def hash_password(password):
    """비밀번호를 SHA-256으로 해싱하는 함수"""
    return hashlib.sha256(password.encode()).hexdigest()

# --- 두음법칙 관련 함수 ---
BASE_CODE, CHOSUNG, JUNGSUNG = 44032, 588, 28
CHOSUNG_LIST = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
JUNGSUNG_LIST = ['ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ']
JONGSUNG_LIST = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

def decompose(syllable):
    if not '가' <= syllable <= '힣':
        return None, None, None
    char_code = ord(syllable) - BASE_CODE
    chosung_index = char_code // CHOSUNG
    jungsung_index = (char_code - (CHOSUNG * chosung_index)) // JUNGSUNG
    jongsung_index = char_code - (CHOSUNG * chosung_index) - (JUNGSUNG * jungsung_index)
    return CHOSUNG_LIST[chosung_index], JUNGSUNG_LIST[jungsung_index], JONGSUNG_LIST[jongsung_index]

def compose(chosung, jungsung, jongsung=''):
    try:
        chosung_index = CHOSUNG_LIST.index(chosung)
        jungsung_index = JUNGSUNG_LIST.index(jungsung)
        jongsung_index = JONGSUNG_LIST.index(jongsung)
        return chr(BASE_CODE + (chosung_index * CHOSUNG) + (jungsung_index * JUNGSUNG) + jongsung_index)
    except (ValueError, IndexError):
        return None

def get_dueum_alternatives(char):
    """두음법칙에 따라 가능한 다음 시작 글자들을 반환합니다."""
    chosung, jungsung, jongsung = decompose(char)
    if chosung is None:
        return []

    alternatives = []
    # 1. 'ㄴ'이 'ㅑ, ㅕ, ㅛ, ㅠ, ㅣ' 앞에 올 때 -> 'ㅇ'으로 변경
    if chosung == 'ㄴ' and jungsung in ['ㅑ', 'ㅕ', 'ㅛ', 'ㅠ', 'ㅣ']:
        alt_char = compose('ㅇ', jungsung, jongsung)
        if alt_char: alternatives.append(alt_char)

    # 2. 'ㄹ'이 단어 첫머리에 올 때 -> 'ㄴ' 또는 'ㅇ'으로 변경
    if chosung == 'ㄹ':
        # 'ㅑ, ㅕ, ㅖ, ㅛ, ㅠ, ㅣ' 앞에서는 'ㅇ'으로
        if jungsung in ['ㅑ', 'ㅕ', 'ㅖ', 'ㅛ', 'ㅠ', 'ㅣ']:
            alt_char = compose('ㅇ', jungsung, jongsung)
            if alt_char: alternatives.append(alt_char)
        # 그 외 모음 앞에서는 'ㄴ'으로
        else:
            alt_char = compose('ㄴ', jungsung, jongsung)
            if alt_char: alternatives.append(alt_char)

    return list(set(alternatives))

# --------------------------------------------------------------------------------
# 게임 및 사용자 관리 함수 (SQLite 버전)
# --------------------------------------------------------------------------------
def get_game_state():
    """SQLite에서 현재 게임 상태를 가져오고, 시간이 되면 주제어를 변경합니다."""
    c.execute("SELECT start_char, last_update_hour, word_history, last_word FROM game_state WHERE id = 1")
    state = c.fetchone()
    game_state = {
        'start_char': state[0],
        'last_update_hour': state[1],
        'word_history': json.loads(state[2]),
        'last_word': state[3]
    }

    current_hour = datetime.now(pytz.timezone('Asia/Seoul')).hour
    if current_hour != game_state['last_update_hour']:
        korean_chars = [chr(code) for code in range(ord('가'), ord('힣') + 1)]
        new_char = random.choice(korean_chars)
        new_history = json.dumps(['시작'])
        c.execute('''
            UPDATE game_state
            SET start_char = ?, last_update_hour = ?, word_history = ?, last_word = ?
            WHERE id = 1
        ''', (new_char, current_hour, new_history, '시작'))
        conn.commit()
        st.toast(f"주제어가 '{new_char}'(으)로 변경되었습니다!", icon="🎉")
        return get_game_state()

    return game_state

def update_game_state(new_word, username):
    """새로운 단어가 추가되었을 때 게임 상태와 사용자 포인트를 업데이트합니다."""
    try:
        conn.execute('BEGIN IMMEDIATE')
        
        c.execute("SELECT word_history FROM game_state WHERE id = 1")
        word_history = json.loads(c.fetchone()[0])

        if new_word in word_history:
            st.warning("이미 사용된 단어입니다.")
            return

        points = len(new_word) * 10
        word_history.append(new_word)
        
        c.execute('''
            UPDATE game_state SET last_word = ?, word_history = ? WHERE id = 1
        ''', (new_word, json.dumps(word_history)))

        c.execute('''
            UPDATE users SET points = points + ? WHERE username = ?
        ''', (points, username))
        
        conn.commit()
        st.success(f"'{new_word}'! 정답! {points} 포인트를 획득했습니다.")
        st.balloons()

    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"데이터베이스 오류: {e}")

def get_user_points(username):
    c.execute("SELECT points FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    return result[0] if result else 0

def get_rankings():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return c.fetchall()

# --------------------------------------------------------------------------------
# UI 렌더링 함수
# --------------------------------------------------------------------------------
def render_login_page():
    st.title("⏰ 실시간 시간제 끝말잇기")
    st.write("매 시간 새로운 글자로 시작하는 끝말잇기에 참여하고 랭킹에 도전하세요!")

    login_tab, signup_tab = st.tabs(["**로그인**", "**회원가입**"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("사용자 이름")
            password = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인"):
                c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
                result = c.fetchone()
                if result and result[0] == hash_password(password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("사용자 이름 또는 비밀번호가 잘못되었습니다.")

    with signup_tab:
        with st.form("signup_form"):
            new_username = st.text_input("사용자 이름")
            new_password = st.text_input("비밀번호", type="password")
            if st.form_submit_button("가입하기"):
                if len(new_username) < 2 or len(new_password) < 4:
                    st.error("사용자 이름은 2자 이상, 비밀번호는 4자 이상이어야 합니다.")
                else:
                    try:
                        c.execute("INSERT INTO users (username, password_hash, points) VALUES (?, ?, 0)",
                                  (new_username, hash_password(new_password)))
                        conn.commit()
                        st.success("회원가입이 완료되었습니다. 로그인해주세요.")
                    except sqlite3.IntegrityError:
                        st.error("이미 존재하는 사용자 이름입니다.")

def render_game_page():
    game_state = get_game_state()
    if not game_state: return

    last_word = game_state.get('last_word', '시작')
    start_char = game_state.get('start_char', '가')
    word_history = game_state.get('word_history', ['시작'])
    
    with st.sidebar:
        st.title("내 정보")
        st.write(f"**{st.session_state.username}** 님")
        st.write(f"**포인트**: {get_user_points(st.session_state.username)} 점")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()
        st.markdown("---")
        st.title("🏆 TOP 10 랭킹")
        for i, (user, points) in enumerate(get_rankings()):
            st.write(f"{i+1}. {user}: {points}점")

    st.title(f"주제어: `{start_char}`")
    st.header(f"현재 단어: **{last_word}**")
    
    next_char = last_word[-1]
    
    with st.form(key='word_input_form'):
        new_word = st.text_input(f"다음 단어를 입력하세요:", placeholder="두 글자 이상...")
        submit_button = st.form_submit_button(label='제출')

    if submit_button and new_word:
        valid_starts = [next_char] + get_dueum_alternatives(next_char)
        
        if new_word[0] not in valid_starts:
            error_msg = f"'{' 또는 '.join(valid_starts)}'(으)로 시작하는 단어를 입력해야 합니다."
            st.error(error_msg)
        elif len(new_word) < 2:
            st.error("단어는 두 글자 이상이어야 합니다.")
        elif new_word not in word_set:
            st.error(f"'{new_word}'는 사전에 없는 단어입니다.")
        else:
            update_game_state(new_word, st.session_state.username)
            st.rerun()
    
    # 입력 안내 메시지
    rule_text = f"**'{next_char}'**"
    if len(valid_starts) > 1:
        alternatives = [f"'{c}'" for c in valid_starts if c != next_char]
        rule_text += f" 또는 {'/'.join(alternatives)} (으)로 시작"
    else:
        rule_text += " (으)로 시작"
    st.info(f"{rule_text}하는 단어를 입력해주세요.")

    st.markdown("---")
    with st.expander("진행된 단어 목록 보기 (최신순)"):
        st.json(word_history[::-1])

# --------------------------------------------------------------------------------
# 메인 실행 로직
# --------------------------------------------------------------------------------
init_db()

if st.session_state.logged_in:
    render_game_page()
else:
    render_login_page()
