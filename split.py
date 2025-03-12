import os
import argparse
import shutil

from pydub import AudioSegment
from tqdm import tqdm
from threading import Thread
from queue import Queue

def worker_thread(q: Queue[tuple[AudioSegment, tuple]]):
    while not q.empty():
        segment, args = q.get()
        segment.export(args[0], format=args[1], parameters=args[2])
        print(args[0])
    

def time_to_milliseconds(time_str):
    h, m, s = map(float, time_str.split(":"))
    return int(h * 3600000 + m * 60000 + s * 1000)


def sanitize_filename(filename):
    # 过滤掉Windows上不允许的字符，并限制文件名的长度
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    return filename[:247]  # 247是为了保证后续可以添加后缀和索引


def split_wav_by_srt(srt_path, wav_path, output_folder, sample_rate, mono, use_subtitle_as_name):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    else:
        print(f'检测到"{output_folder}" 已存在，执行删除')
        shutil.rmtree(output_folder)
        os.makedirs(output_folder)

    mapping = []
    q: Queue[tuple[AudioSegment, tuple]] = Queue()
    
    with open(srt_path, 'r', encoding='utf-8') as file:
        content = file.read()
        blocks = content.strip().split("\n\n")
        audio: AudioSegment = AudioSegment.from_wav(wav_path)
        prj_name = os.path.basename(wav_path)[:-4]

        for block in tqdm(blocks, desc=f"Processing {prj_name}"):
            lines = block.split("\n")
            times = lines[1].split("-->")
            start_time, end_time = [time_to_milliseconds(t.strip().replace(",", ".")) for t in times]
            subtitle = " ".join(lines[2:])

            segment = audio[start_time:end_time]

            if mono:
                segment = segment.set_channels(1)

            if sample_rate:
                segment = segment.set_frame_rate(sample_rate)

            if use_subtitle_as_name:
                filename = sanitize_filename(subtitle) + ".wav"
                idx = 1
                while os.path.exists(os.path.join(output_folder, prj_name, filename)):
                    filename = sanitize_filename(subtitle) + f"_{idx}.wav"
                    idx += 1
            else:
                filename = f"{start_time}_{end_time}.wav"
                mapping.append(f"{filename}|{subtitle}")

            if not os.path.exists(os.path.join(output_folder, prj_name)):
                os.makedirs(os.path.join(output_folder, prj_name))
            # segment.export(os.path.join(output_folder, prj_name, filename), format="wav", parameters=["-sample_fmt", "s16"])
            q.put((segment, (os.path.join(output_folder, prj_name, filename), "wav", ["-sample_fmt", "s16"])))

    CPUS = os.cpu_count() or 1
    for _ in range(CPUS):
        t = Thread(target=worker_thread, args=(q,))
        t.start()
    
    if not use_subtitle_as_name:
        with open(os.path.join(output_folder, prj_name, "mapping.list"), "a", encoding="utf-8") as f:
            for line in mapping:
                f.write(line + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split WAVs based on SRT timings in a folder")
    parser.add_argument("--input_folder", type=str, default="input", help="Path to the input folder containing SRT and WAV files")
    parser.add_argument("--output_folder", type=str, default="output", help="Output folder path")
    parser.add_argument("--sample_rate", type=int, default=44100, help="Sample rate for output WAVs")
    parser.add_argument("--mono", action="store_true", help="Convert to mono")
    parser.add_argument("--use_subtitle_as_name", action="store_true", help="Use subtitle as filename")

    args = parser.parse_args()

    for root, dirs, files in os.walk(args.input_folder):
        for file in files:
            if file.endswith(".srt"):
                wav_file = file.replace(".srt", ".wav")
                if wav_file in files:
                    split_wav_by_srt(os.path.join(root, file), os.path.join(root, wav_file), args.output_folder,
                                     args.sample_rate, args.mono, args.use_subtitle_as_name)
