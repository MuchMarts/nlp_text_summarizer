import os
import pdfplumber
import spacy
import re
import logging
import yaml

#
#   If you are reading this, you should probably know that this code is not good
#   and is not meant to be used in production. It is a quick and dirty script to
#   extract and clean text from MIT OpenCourseWare PDFs. For an assignment.
#   Please do not use this code as an example of good coding practices.
#   Alot of the code is copied from various sources and modified to fit the needs of
#   this script. And much of the regex is vibes-based and vibe-coded.
#


nlp = spacy.load("en_core_web_sm")
logging.getLogger('pdfminer').setLevel(logging.ERROR)

#
#   Helper functions for processing MIT OpenCourseWare PDFs
#

def remove_ocw_preamble(text):
    return re.sub(
        r"(MITOCW\s*\|.*?ocw\.mit\.edu\s*\.)",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

def clean_punctuation(text):
    text = re.sub(r",\s*,", ", ", text)        # remove double commas
    text = re.sub(r"\s{2,}", " ", text)        # collapse extra spaces
    text = re.sub(r"\s+([,.!?])", r"\1", text) # remove space before punctuation
    return text

def clean_transcript(text):
    text = remove_ocw_preamble(text)
    # Remove speaker labels and others
    text = re.sub(r"^[A-Z ]{2,}:\s*", "", text, flags=re.MULTILINE)
    # Remove duplicate words (like stutters)
    text = re.sub(r'\b(\w+),\s+\1\b', r'\1', text)
    # Run through spaCy
    doc = nlp(text)
    # Remove redundant whitespaces and short sentences
    cleaned = [
        sent.text.strip() for sent in doc.sents
        if len(sent.text.split()) >= 5
    ]
    # Remove filler words and interjections
    cleaned = [
        " ".join(token.text for token in nlp(sent) if token.pos_ != "INTJ" and token.text.lower() not in {"uh", "um", "you know", "so", "okay"})
        for sent in cleaned
    ]
    # Clean punctuation
    cleaned = [clean_punctuation(sent) for sent in cleaned]

    return "\n".join(cleaned)

def normalize_line_breaks(text):
    # Remove hyphenated line breaks (e.g., "inter-\npretation" → "interpretation")
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    # Replace all line breaks that are NOT followed by another line break (i.e., not a paragraph break)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Normalize multiple newlines to two (optional, depending on spacing needs)
    text = re.sub(r'\n{2,}', '\n\n', text)

    return text

def extract_text_from_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    text = normalize_line_breaks(text)
    return text.strip()

def process_pdf(pdf_path):
    try:
        text = extract_text_from_pdf(pdf_path)
        cleaned_text = clean_transcript(text)
        save_to_txt(cleaned_text, pdf_path.replace(".pdf", ".txt"))
        return True
    except Exception as e:
        print(f"Error processing PDF {pdf_path}: {e}")
        return None

def save_to_txt(text, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

def clean_notes(text):
    text = re.sub(r"\(cid:\d+\)", "", text)
    text = re.sub(r"(?m)^\s*\d*\.*\d+ LECTURE \d+(?: \d+)?\s*$", "", text)
    text = re.sub(r"\b\d*\.*\d+ LECTURE \d+\b", "", text)
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    text = re.sub(r"[ \t]*[◦•]\s*", r"\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
#
# Read and match lecture transcripts and notes
#

INPUT_DIR = "MIT OpenCourseWare"
OUTPUT_DIR = "TEST"
lecture_map = {}

transcript_regex = r"lec_(\d+)_t\.pdf"
note_regex = r"_Lec(\d+)\.pdf"

transcript_files = [f for f in os.listdir(INPUT_DIR) if re.match(transcript_regex, f)]
note_files = [f for f in os.listdir(INPUT_DIR) if re.search(note_regex, f)]

# Build transcript dict by lecture number
transcripts = {}
for file in transcript_files:
    match = re.match(transcript_regex, file)
    if match:
        lec_num = int(match.group(1))
        transcripts[lec_num] = file

# Build notes dict by lecture number
notes = {}
for file in note_files:
    match = re.search(note_regex, file)
    if match:
        lec_num = int(match.group(1))
        notes[lec_num] = file


# Match transcripts and notes by lecture number 
# and process them
for lec_num in sorted(set(transcripts) & set(notes)):
    transcript_pdf = os.path.join(INPUT_DIR, transcripts[lec_num])
    notes_pdf = os.path.join(INPUT_DIR, notes[lec_num])
    print(f"Processing lecture {lec_num}...")
    try:
        raw_transcript = extract_text_from_pdf(transcript_pdf)
        cleaned_transcript = clean_transcript(raw_transcript)
        transcript_txt = os.path.join(OUTPUT_DIR, "transcript_lec_" + str(lec_num) + ".txt")
        save_to_txt(cleaned_transcript, transcript_txt)

        raw_notes = extract_text_from_pdf(notes_pdf)
        cleaned_notes = clean_notes(raw_notes)
        notes_txt = os.path.join(OUTPUT_DIR, "notes_lec_" + str(lec_num) + ".txt")
        save_to_txt(cleaned_notes, notes_txt)

        lecture_map[transcript_txt] = {
            "summary": notes_txt
        }

    except Exception as e:
        print(f"[!] Error processing lecture {lec_num}: {e}")


print("Processing complete. Lecture map:")
for transcript, details in lecture_map.items():
    print(f"{transcript} -> {details['summary']}")

output_data = {
    "files": [
        {
            "original": transcript,
            "summary": details["summary"]
        }
        for transcript, details in lecture_map.items()
    ]
}

with open("lecture_summary_map.yaml", "w") as yaml_file:
    yaml.dump(output_data, yaml_file, sort_keys=False)

print("Processing complete. YAML file 'lecture_summary_map.yaml' written.")