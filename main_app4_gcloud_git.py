import streamlit as st
import re
import os
import time
from pydub import AudioSegment
import requests
import random
from pydub.utils import mediainfo
from google.cloud import texttospeech_v1 as texttospeech
import tempfile
from google.oauth2 import service_account
import json
import base64
import io
import logging
import uuid

logging.basicConfig(level=logging.INFO, filename='app.log', filemode='w')

# 환경 변수에서 인증 정보를 가져옵니다.
credentials_str = os.environ['GCP_CREDENTIALS']
credentials_dict = json.loads(credentials_str)

# credentials_dict를 사용하여 Google 서비스 계정 인증 정보를 얻습니다.
credentials = service_account.Credentials.from_service_account_info(credentials_dict)

# Text-to-Speech 클라이언트를 초기화합니다.
client = texttospeech.TextToSpeechClient(credentials=credentials)

@st.cache_data
def load_conversations_and_modifications():
    # Directly load from raw GitHub URLs
    conversations_url = "https://raw.githubusercontent.com/weon-seongjae/conv/master/conversations.json"
    modifications_url = "https://raw.githubusercontent.com/weon-seongjae/conv/master/chapter_modification.json"

    conversations_response = requests.get(conversations_url)
    conversations_data = conversations_response.json()
    for chapter in conversations_data:
        for conversation in chapter['conversations']:
            # 'message'가 문자열이라면 리스트로 변환
            if isinstance(conversation['message'], str):
                conversation['message'] = [conversation['message']]

    modifications_response = requests.get(modifications_url)
    modifications_data = modifications_response.json()

    modifications_dict = {modification['chapter']: modification for modification in modifications_data}

    return conversations_data, modifications_dict

knowledge_base, modifications_dict = load_conversations_and_modifications()

def synthesize_speech(text, voice_name, male_voices_mapping, female_voices_mapping):
    client = texttospeech.TextToSpeechClient(credentials=credentials)
    input_text = texttospeech.SynthesisInput(text=text)
    
    # 음성 이름을 기반으로 성별 결정
    if voice_name in male_voices_mapping.values():
        ssml_gender = texttospeech.SsmlVoiceGender.MALE
    elif voice_name in female_voices_mapping.values():
        ssml_gender = texttospeech.SsmlVoiceGender.FEMALE
    else:
        # 이 경우에는 어떤 작업을 할지 정해야 합니다. 여기에서는 예외를 발생시킵니다.
        raise ValueError(f"Unsupported voice_name: {voice_name}")

    voice_params = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=voice_name,
        ssml_gender=ssml_gender
    )

    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=input_text, voice=voice_params, audio_config=audio_config)
    return response


def speak_and_mixed(text, voice_name, male_voices_mapping, female_voices_mapping, is_question=False):
    clean_text = re.sub('<[^<]+?>', '', text)
    response = synthesize_speech(clean_text, voice_name, male_voices_mapping, female_voices_mapping)
    audio = AudioSegment.from_file(io.BytesIO(response.audio_content), format='mp3')
    audio_length = len(audio) / (16000 * 2)  # 16kHz, 16-bit mono PCM 음성 데이터를 가정합니다.

    base64_audio = base64.b64encode(response.audio_content).decode('utf-8')

    return base64_audio, clean_text, audio_length


def prepare_speakers_and_messages(selected_chapter, chapter_conversations, modifications_dict):
    speakers_and_messages = [{'chapter': selected_chapter, 'speaker': message['speaker'], 'message': message['message']} 
                         for message in chapter_conversations 
                         if message['speaker'] == 'user']
    speakers_and_messages.insert(0, {'chapter': selected_chapter, 'speaker': "user", 'message': ""})

    if selected_chapter in modifications_dict:
        for add in modifications_dict[selected_chapter]['add']:
            speakers_and_messages.append({'chapter': selected_chapter, 'speaker': add['speaker'], 'message': add['message']})

        for remove in modifications_dict[selected_chapter]['remove']:
            speakers_and_messages = [i for i in speakers_and_messages if not (i['speaker'] == remove['speaker'] and remove['message'] in i['message'])]


    return speakers_and_messages

def handle_chapter_and_conversation_selection(knowledge_base):
    chapters = [data['chapter'] for data in knowledge_base]

    if "selected_chapter" not in st.session_state or st.session_state.selected_chapter not in chapters:
        st.session_state.selected_chapter = chapters[0]

    if st.session_state.selected_chapter in chapters:
        selected_chapter = st.selectbox(
            "Choose a chapter:",
            chapters,
            index=chapters.index(st.session_state.selected_chapter),
        )
        if st.session_state.selected_chapter != selected_chapter:
            st.session_state.selected_chapter = selected_chapter
            if "selected_message" in st.session_state:
                del st.session_state.selected_message
            if "chat_history" in st.session_state:
                del st.session_state.chat_history
                st.experimental_rerun()

    chapter_conversations = next((data['conversations'] for data in knowledge_base if data['chapter'] == st.session_state.selected_chapter), None)

    speakers_and_messages = prepare_speakers_and_messages(st.session_state.selected_chapter, chapter_conversations, modifications_dict)

    all_messages = [""]
    all_messages += [" ".join(sm['message']) if isinstance(sm['message'], list) else sm['message'] for sm in speakers_and_messages if sm['message']]


    if not all_messages:
        raise ValueError("all_messages is empty. Check the function prepare_speakers_and_messages.")

    if "" not in all_messages:
        raise ValueError("Empty string is not in all_messages. Check the function prepare_speakers_and_messages.")

    if "selected_message" not in st.session_state or st.session_state.selected_message not in all_messages:
        st.session_state.selected_message = all_messages[0]

    if st.session_state.selected_message in all_messages:
        selected_message = st.selectbox(
            "Choose a conversation:",
            all_messages,
            index=all_messages.index(st.session_state.selected_message) if st.session_state.selected_message != "" else 0,
        )
        if st.session_state.selected_message != selected_message:
            st.session_state.selected_message = selected_message
            st.experimental_rerun()

    if st.session_state.selected_chapter and st.session_state.selected_message and st.session_state.selected_message != "":
        chapter_name = st.session_state.selected_chapter
        chapter_data = next(chap_data for chap_data in knowledge_base if chap_data["chapter"] == chapter_name)
        speakers_and_messages = chapter_data["conversations"]

        return chapter_name, chapter_data, speakers_and_messages
    return None, None, None


def display_chat_history(chapter_data, auto_play_consent, male_voices_mapping, female_voices_mapping, question_voice_name, answer_voice_name, css_style=None):

    final_html = ""

    if not hasattr(st.session_state, "selected_conversations"):
        st.session_state.selected_conversations = []

    selected_message = st.session_state.selected_message
    selected_conversation = None

    conversations = chapter_data["conversations"]
    for idx, conv in enumerate(conversations[:-1]):  # 마지막 대화를 제외하고 반복
        for message_idx, msg in enumerate(conv["message"]):
            if msg == selected_message:
                selected_conversation = [conversations[idx], conversations[idx + 1]]  # 선택된 대화와 그 다음 대화를 할당
                break
        if selected_conversation:
            break

    if not hasattr(st.session_state, "chat_history"):
        st.session_state.chat_history = []

    if selected_conversation:
        st.session_state.chat_history = []
        question_messages = selected_conversation[0]['message']
        response_messages = selected_conversation[1]['message']

        question_message = question_messages[0]
        question_base64_audio, _, question_audio_length = speak_and_mixed(question_message, question_voice_name, male_voices_mapping, female_voices_mapping)
        
        response_message = random.choice(response_messages)
        response_base64_audio, _, response_audio_length = speak_and_mixed(response_message, answer_voice_name, male_voices_mapping, female_voices_mapping)

        # 남자 성우의 경우 아이콘 지정
        if question_voice_name in male_voices_mapping.values():
            question_icon = "👨‍🦰"
        else:
            question_icon = "👩‍🦰"

        # 남자 성우의 경우 아이콘 지정
        if answer_voice_name in male_voices_mapping.values():
            answer_icon = "👨"
        else:
            answer_icon = "👩"

        if auto_play_consent:
            # pydub을 사용하여 질문과 답변 음성을 합칩니다
            question_audio = AudioSegment.from_file(io.BytesIO(base64.b64decode(question_base64_audio)), format='mp3')
            answer_audio = AudioSegment.from_file(io.BytesIO(base64.b64decode(response_base64_audio)), format='mp3')
            silence = AudioSegment.silent(duration=1000)
            combined_audio = question_audio + silence + answer_audio

            combined_buffer = io.BytesIO()
            combined_audio.export(combined_buffer, format="mp3")
            data_url = f"data:audio/mp3;base64,{base64.b64encode(combined_buffer.getvalue()).decode('utf-8')}"
            audio_tag = f'<audio autoplay src="{data_url}" style="display: none;"></audio>'
            st.markdown(audio_tag, unsafe_allow_html=True)

            # 질문 음성과 답변 음성이 모두 끝나기 전에 질문 텍스트와 답변 텍스트 동시 출력
            st.markdown(f'<div class="question-text">{question_icon} {question_message}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="answer-text">{answer_icon} {response_message}</div>', unsafe_allow_html=True)

        else:
            st.write("Error: Selected message and the corresponding answer not found.")
            return

    st.markdown(final_html, unsafe_allow_html=True)
    st.markdown(css_style, unsafe_allow_html=True)

def main():
    st.title("Daily English Conversations")

    css_style = """
    <style>
        /* 질문 텍스트 스타일 */
        .question-text {
            font-size: 35px;
            padding: 10px 15px;
            border-radius: 10px;
            margin: 5px 0;
            box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.1);
        }

        /* 답변 텍스트 스타일 */
        .answer-text {
            font-size: 35px;
            padding: 10px 15px;
            border-radius: 10px;
            margin: 5px 0;
            box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.1);
        }
    </style>
    """
    st.markdown(css_style, unsafe_allow_html=True)

    male_voices_mapping = {
        "Tom(남성)": "en-US-Polyglot-1",
        "Bob(남성)": "en-US-Standard-A",
        "Bill(남성)": "en-US-Standard-B",
        "Jim(남성)": "en-US-Standard-D",
        "John(남성)": "en-US-Standard-I",
        "Jack(남성)": "en-US-Standard-J"
    }

    female_voices_mapping = {
        "Beth(여성)": "en-US-Standard-C",
        "Mia(여성)": "en-US-Standard-E",
        "Ivy(여성)": "en-US-Standard-F",
        "Emma(여성)": "en-US-Standard-G",
        "Alice(여성)": "en-US-Standard-H"
    }

    st.sidebar.markdown("<strong>질문 성우 선택</strong>", unsafe_allow_html=True)
    voices_list = list(male_voices_mapping.keys()) + list(female_voices_mapping.keys())
    selected_question_voice = st.sidebar.radio("성우 선택", voices_list)

    st.sidebar.markdown("<strong>답변 성우 선택</strong>", unsafe_allow_html=True)
    selected_answer_voice = st.sidebar.radio("성우 선택", voices_list, key="answer_voice")

    auto_play_consent = st.checkbox("영어회화 프로그램 진행에 동의합니다.")
    
    if not auto_play_consent:
        st.warning("프로그램을 진행하려면 동의해야 합니다.")
        return

    _, chapter_data, speakers_and_messages = handle_chapter_and_conversation_selection(knowledge_base)

    if selected_question_voice in male_voices_mapping:
        question_voice_name = male_voices_mapping[selected_question_voice]
    else:
        question_voice_name = female_voices_mapping[selected_question_voice]

    if selected_answer_voice in male_voices_mapping:
        answer_voice_name = male_voices_mapping[selected_answer_voice]
    else:
        answer_voice_name = female_voices_mapping[selected_answer_voice]

    if speakers_and_messages and chapter_data:
        display_chat_history(chapter_data, auto_play_consent, male_voices_mapping, female_voices_mapping, question_voice_name, answer_voice_name, css_style)

def safe_delete(file):
    for _ in range(10):
        try:
            os.remove(file)
            print(f"Successfully deleted {file}")
            break
        except Exception as e:
            print(f"Failed to delete {file}: {e}") 
            # time.sleep(0.5)

if __name__ == "__main__":
    main()
    # for file in temp_files:
    #     safe_delete(file)