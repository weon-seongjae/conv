import streamlit as st
from gtts import gTTS
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


def load_conversations_and_modifications():
    with open("conversations.json", "r", encoding='utf-8') as file:
        conversations_data = json.load(file)
        for chapter in conversations_data:
            for conversation in chapter['conversations']:
                # 'message'가 문자열이라면 리스트로 변환
                if isinstance(conversation['message'], str):
                    conversation['message'] = [conversation['message']]

    with open("chapter_modification.json", "r", encoding='utf-8') as file:
        modifications_data = json.load(file)

    modifications_dict = {modification['chapter']: modification for modification in modifications_data}

    return conversations_data, modifications_dict

knowledge_base, modifications_dict = load_conversations_and_modifications()

temp_files = []
audio_directory = os.path.abspath('./audio')

def synthesize_speech(text, filename):
    tts = gTTS(text, lang='en')
    filename = f"./audio/{filename}"
    tts.save(filename)
    return filename

def speak_and_mixed(text):
    if text.startswith("./audio_"):
        return [], [], 0

    audio_urls = []
    text_chunks = []

    clean_text = re.sub('<[^<]+?>', '', text)
    unique_id = uuid.uuid4()
    filename = f"0_{unique_id}.mp3"
    audio_path = synthesize_speech(clean_text, filename)
    # audio_url = f"http://127.0.0.1:8001/audio/{os.path.basename(audio_path)}"
    audio_url = f"https://a177-1-222-123-226.ngrok-free.app/audio/{os.path.basename(audio_path)}"


    # 음성 파일의 길이를 직접 여기서 계산합니다.
    audio = AudioSegment.from_mp3(audio_path)
    audio_length = len(audio) / 1000

    # 음성 파일을 버퍼 디렉토리로 복사합니다.
    # buffer_path = os.path.join('./audio_buffer', filename)
    # shutil.copyfile(audio_path, buffer_path)

    print(f"Generated audio for conversation: '{clean_text}', Audio URL: '{audio_url}', Audio Length: {audio_length}")
    
    audio_urls.append(audio_url)
    text_chunks.append(clean_text)

    return audio_urls, text_chunks, audio_length


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

# def pre_buffer_audio_files(speakers_and_messages):
#     print(f"speakers_and_messages {speakers_and_messages}")
#     buffer_dir = "./audio_buffer"
    
#     print(f"Creating buffer directory: {buffer_dir}")
#     os.makedirs(buffer_dir, exist_ok=True)
#     buffer_dir = os.path.abspath("./audio_buffer")
#     print(buffer_dir)

#     # 모든 사용자 메시지에 대한 음성 파일을 미리 생성합니다.
#     for sm in speakers_and_messages:
#         if sm['message']:
#             text = sm['message']
#             unique_id = uuid.uuid4()
#             filename = f"{unique_id}.mp3"
#             audio_path = synthesize_speech(text, filename)
#             os.rename(audio_path, os.path.join(buffer_dir, filename))

# def get_pre_buffered_audio_url(message):
#     buffer_dir = "./audio_buffer"
#     for filename in os.listdir(buffer_dir):
#         if message in filename:
#             return f"http://127.0.0.1:8001/audio_buffer/{filename}"

#     return None

css_style = """
<style>
.styled-message {
    # background-color: white;
    border-radius: 0px;
    padding: 0;
    margin: 5px;  /* Adjust margin to control the gap */
    box-shadow: none;  /* Remove shadow effect */
}
.question-dialogue-gap {
    margin: 0; /* Add a larger margin for the gap */
}
</style>
"""

def display_chat_history(chapter_data):

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
        st.markdown("<hr>", unsafe_allow_html=True)
        for i, msg in enumerate(conv["conversation"]):
            messages = msg['message']  # Assume messages is a list
            message = ""
            
            # If bot and message is in modifications_dict 'add', then it's a question
            is_bot_question = (msg['speaker'] == 'bot' and
                               any(add['message'] == messages[0] for add in modifications_dict.get(chapter_data["chapter"], {}).get('add', [])))
            
            if is_bot_question:
                print("User is the speaker")
                message = messages[0]  # bot이 질문하는 경우 첫 번째 메시지를 질문으로 선택합니다.
            else:
                if msg['speaker'] == 'user':
                    print("User is the speaker")
                    message = random.choice(messages)  # 사용자가 질문하는 경우 첫 번째 메시지를 질문으로 선택합니다.
                else:
                    print("Bot is the speaker but not asking a question")
                    print(f"Available messages for random selection: {messages}")
                    message = messages[0]
            
            icon = "👩‍🦰" if msg['speaker'] == 'user' else "👩"
            message = message.replace('\n', '  \n')
            styled_message = f'<div class="styled-message">{icon} {message}</div>'

            if i == 0 and msg['speaker'] == 'user' and idx > 0:
                styled_message += '<div class="question-dialogue-gap"></div>'  # Add a gap after the question

            # if i == 0 and idx > 0:
            #     styled_message += '<div class="question-dialogue-gap"></div>'

            if conv["is_new"]:
                audio_urls, text_chunks, audio_length = speak_and_mixed(message)
                for audio_url in audio_urls:
                    audio_tag = f'<audio autoplay src="{audio_url}" style="display: none;"></audio>'
                    st.markdown(audio_tag, unsafe_allow_html=True)
                    time.sleep(audio_length)

            st.markdown(styled_message, unsafe_allow_html=True)

            # Deleting audio files
            if conv["is_new"]:
                for audio_url in audio_urls:
                    filename = audio_url.split('/')[-1]
                    requests.post(f"http://127.0.0.1:8001/delete/audio/{filename}")

        # Once a conversation has been displayed, it's not new anymore
        if conv["is_new"]:
            st.session_state.chat_history[idx]["is_new"] = False

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