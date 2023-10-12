import streamlit as st
import re
import json
from PIL import Image
import os
import time
import tempfile
import uuid
from pydub import AudioSegment
import requests
import random
from pydub.utils import mediainfo
from google.cloud import texttospeech_v1 as texttospeech
import tempfile


os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = json.dumps(st.secrets['MY_SECRET'])

@st.cache_data
def load_conversations_and_modifications():
    # Directly load from raw GitHub URLs
    conversations_url = "https://raw.githubusercontent.com/weon-seongjae/conv/main/conversations.json"
    modifications_url = "https://raw.githubusercontent.com/weon-seongjae/conv/main/chapter_modification.json"

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

temp_files = []

def synthesize_speech(text, filename, voice_type):
    client = texttospeech.TextToSpeechClient()

    input_text = texttospeech.SynthesisInput(text=text)

    if voice_type == "male":
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-D",
            ssml_gender=texttospeech.SsmlVoiceGender.MALE
        )
    else:
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Neural2-C",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
        )

    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = client.synthesize_speech(
        input=input_text,
        voice=voice_params,
        audio_config=audio_config
    )

    # 임시 파일로 음성 데이터 저장
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        temp_file.write(response.audio_content)
        print(f"Created temp file at: {temp_file.name}")  # 경로 출력
        if os.path.exists(temp_file.name):
            print(f"File {temp_file.name} exists!")  # 파일이 실제로 존재하는지 확인
        else:
            print(f"File {temp_file.name} does not exist!")
        temp_files.append(temp_file.name)  # temp_files에 임시 파일 경로 추가
        return temp_file.name

def speak_and_mixed(text, is_question=False):
    clean_text = re.sub('<[^<]+?>', '', text)
    unique_id = uuid.uuid4()
    filename = f"question_{unique_id}.mp3" if is_question else f"answer_{unique_id}.mp3"
    audio_path = synthesize_speech(clean_text, filename, "male" if is_question else "female")
    print(f"Audio path from speak_and_mixed: {audio_path}")
    if os.path.exists(audio_path):
        print(f"File {audio_path} exists!")  # 파일이 실제로 존재하는지 확인
    else:
        print(f"File {audio_path} does not exist!")
    temp_files.append(audio_path)

    audio = AudioSegment.from_mp3(audio_path)
    audio_length = len(audio) / 1000

    return audio_path, clean_text, audio_length


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

css_style = """
<style>
    .styled-message {
        font-size: 30px;
        background-color: #f0f0f0;
        padding: 5px;
        margin: 5px 0;
        line-height: 5; /* Adjust the line spacing */
    }
    .question-dialogue-gap {
        height: 20px;
    }
</style>
"""

def display_chat_history(chapter_data):
    final_html = ""

    if not hasattr(st.session_state, "selected_conversations"):
        st.session_state.selected_conversations = []

    selected_message = st.session_state.selected_message
    print(f"Selected message: {selected_message}")
    selected_conversation = None

    selected_message = st.session_state.selected_message

    conversations = chapter_data["conversations"]
    for idx, conv in enumerate(conversations[:-1]): # 마지막 대화를 제외하고 반복
        for message_idx, msg in enumerate(conv["message"]):
            if msg == selected_message:
                selected_conversation = [conversations[idx], conversations[idx + 1]] # 선택된 대화와 그 다음 대화를 할당
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
        response_message = random.choice(response_messages)

        # 새 대화 삽입
        st.session_state.chat_history.insert(0, {
            "conversation": [{"speaker": "user" if selected_conversation[0]['speaker'] == "bot" else "bot", "message": [question_message]},
                        {"speaker": "bot" if selected_conversation[0]['speaker'] == "bot" else "user", "message": [response_message]}],
            "is_new": True})

        # 선택된 대화 기록
        st.session_state.selected_conversations.append(selected_conversation)
    else:
        st.write("Error: Selected message and the corresponding answer not found.")
        return

    # for 루프 시작 전에 변수를 초기화
    audio_controls = ""

    for idx, conv in enumerate(st.session_state.chat_history):
        question_message = conv["conversation"][0]['message'][0]

        if conv["is_new"]:
            question_audio_path, _, question_audio_length = speak_and_mixed(question_message, is_question=True)

            audio_tag = f'<audio autoplay src="{question_audio_path}" style="display: none;"></audio>'
            st.markdown(audio_tag, unsafe_allow_html=True)
            time.sleep(question_audio_length)

        for i, msg in enumerate(conv["conversation"]):
            messages = msg['message']
            message = messages[0]
            icon = "👩‍🦰" if msg['speaker'] == 'user' else "👩"
            message = message.replace('\n', ' \n')
            styled_message = f'<div class="styled-message">{icon} {message}</div>'

            if i == 0 and idx > 0:
                styled_message += '<div class="question-dialogue-gap"></div>'

            final_html += styled_message # Append each message to final_html

            if i == 1:
                response_audio_path, _, response_audio_length = speak_and_mixed(message, is_question=False)
                audio_tag = f'<audio autoplay src="{response_audio_path}" style="display: none;"></audio>'
                st.markdown(audio_tag, unsafe_allow_html=True)
                time.sleep(response_audio_length)

            if conv["is_new"]:
                st.session_state.chat_history[idx]["is_new"] = False

        # Once a conversation has been displayed, it's not new anymore
        if conv["is_new"]:
            st.session_state.chat_history[idx]["is_new"] = False

    # 임시 파일 삭제
    for file_path in temp_files:
        if os.path.exists(file_path):
            os.remove(file_path)
    temp_files.clear()

    st.markdown(final_html, unsafe_allow_html=True)
    st.markdown(css_style, unsafe_allow_html=True)

def main():
    st.title("Daily English Conversations")

    _, chapter_data, speakers_and_messages = handle_chapter_and_conversation_selection(knowledge_base)

    if speakers_and_messages and chapter_data:
        display_chat_history(chapter_data)

def safe_delete(file):
    for _ in range(10):
        try:
            os.remove(file)
            print(f"Successfully deleted {file}")
            break
        except Exception as e:
            print(f"Failed to delete {file}: {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    main()
    for file in temp_files:
        safe_delete(file)