from groq import Groq
from dotenv import load_dotenv
import os
import json

load_dotenv()

api_key = os.getenv("GROQ_KEY")
if not api_key:
    raise ValueError("GROQ_KEY manquante dans le fichier .env")
client = Groq(api_key=api_key)


def read_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def classify_mail(mail_content: str) -> dict:
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": read_file("context.txt")},
            {
                "role": "user",
                "content": f'{read_file("prompt.txt")}\nVoici le contenu du mail : {mail_content}',
            },
        ],
        response_format={"type": "json_object"},
        model="llama-3.3-70b-versatile",
        temperature=0,
    )
    result = json.loads(response.choices[0].message.content)
    return result


if __name__ == "__main__":
    mail_content = read_file("mail.txt")
    mail_classification = classify_mail(mail_content)
    print(mail_classification["urgence"])
    print(mail_classification["categorie"])
    print(mail_classification["résumé"])
