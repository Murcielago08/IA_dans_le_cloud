# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
# pip install transformers
# pip install datasets
# pip install librosa
# pip install transformers
# pip3 install ffmpeg-python
# necessite ffmepg installé. Sous windows, utiliser winget install ffmpeg et reboot (ou wsl)

import torch
from transformers import pipeline
import ffmpeg
import math

# ============================================================
# ETAPE 1 : extraire la piste audio de la video source (input.mp4)
# -> produit un fichier .wav exploitable par le modele de transcription
# ============================================================
input_video = "input.mp4"
input_video_name = input_video.replace(".mp4", "")
extracted_audio = f"audio-{input_video_name}.wav"
stream = ffmpeg.input(input_video)
stream = ffmpeg.output(stream, extracted_audio)
ffmpeg.run(stream, overwrite_output=True)  # lance la commande ffmpeg (equivalent a l'appel en ligne de commande)

# ============================================================
# ETAPE 2 : charger le modele de transcription (Whisper) sur GPU
# -> "cuda:0" = premiere carte graphique disponible
# -> torch.float16 reduit l'empreinte memoire / accelere l'inference sur GPU
# ============================================================
device = "cuda:0"
whisper = pipeline("automatic-speech-recognition",
                   "openai/whisper-medium.en",
                   torch_dtype=torch.float16,
                   device=device)

# ============================================================
# ETAPE 3 : transcrire l'audio
# -> chunk_length_s=28 : Whisper traite l'audio par segments de 28s
#    (limite du modele ~30s par passage)
# -> return_timestamps=True : renvoie le texte + les horodatages de chaque segment
# -> "transcription" contient : transcription["text"] (texte complet)
#    et transcription["chunks"] (liste de segments avec timestamps)
# ============================================================
transcription = whisper(extracted_audio, chunk_length_s=28, return_timestamps=True)

def format_time(seconds):
    # convertit un nombre de secondes (float) en format SRT: HH:MM:SS,mmm
    hours = math.floor(seconds / 3600)
    seconds %= 3600
    minutes = math.floor(seconds / 60)
    seconds %= 60
    milliseconds = round((seconds - math.floor(seconds)) * 1000)
    seconds = math.floor(seconds)
    formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:01d},{milliseconds:03d}"

    return formatted_time


# ============================================================
# ETAPE 4 : construire le fichier de sous-titres au format .srt
# -> chaque "chunk" renvoye par Whisper devient un bloc de sous-titre
#    numerote, avec son intervalle de temps et son texte
# -> "offset" corrige les timestamps : quand Whisper redemarre un nouveau
#    segment de 28s, ses timestamps repartent de 0, donc on decale le
#    temps cumule pour que les sous-titres restent synchro sur toute la video
# ============================================================
subtitle_file = f"sub-{input_video_name}.en.srt"
text = ""
offset=0
for index, chunk in enumerate(transcription["chunks"]):
    start = offset + chunk["timestamp"][0]
    end = offset + chunk["timestamp"][1]
    if start > end:
        # incoherence de timestamp = marqueur du debut d'un nouveau segment de 28s
        # chez Whisper -> on avance l'offset et on saute ce chunk (pas de texte utile)
        offset += 28
        continue
    text_chunk = chunk["text"]
    segment_start = format_time(start)
    segment_end = format_time(end)
    # format standard .srt : numero de bloc / plage horaire / texte / ligne vide
    text += f"{str(index + 1)} \n"
    text += f"{segment_start} --> {segment_end} \n"
    text += f"{text_chunk} \n"
    text += "\n"

f = open(subtitle_file, "w")
f.write(text)
f.close()


# ============================================================
# ETAPE 5 : reinjecter les sous-titres dans la video
# -> deux modes possibles (controles par embedded_subtitle) :
#    - piste de sous-titres separee (soft subs), activable/desactivable
#      par le lecteur video, sans reencoder l'image/le son ("c": "copy")
#    - sous-titres "brules" dans l'image (hard subs) via le filtre vf=subtitles=...
#      (necessite un reencodage video, plus lent)
# ============================================================
video_input_stream = ffmpeg.input(input_video)
subtitle_input_stream = ffmpeg.input(subtitle_file)
output_video = f"output.mp4"
subtitle_track_title = subtitle_file.replace(".srt", "")

# Change if subtitile must be umbedded or not in the video
embedded_subtitle = False
if not embedded_subtitle:
    # mode "soft subs" : copie video/audio telles quelles (c: copy) + ajoute
    # une piste de sous-titres mov_text (format compatible mp4), avec metadonnees
    # de langue/titre sur les pistes
    stream = ffmpeg.output(
        video_input_stream, subtitle_input_stream, output_video, **{"c": "copy", "c:s": "mov_text"},
        **{"metadata:s:s:0": "language=en",
        "metadata:s:s:1": f"title={subtitle_track_title}"}
    )
    ffmpeg.run(stream, overwrite_output=True)
else:
    # mode "hard subs" : incruste les sous-titres directement dans l'image
    stream = ffmpeg.output(video_input_stream, output_video,
                           vf=f"subtitles={subtitle_file}")

    ffmpeg.run(stream, overwrite_output=True)

# affiche la transcription complete dans la console a titre de verification
print(transcription["text"])
