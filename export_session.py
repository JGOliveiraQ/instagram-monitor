"""
Gera o base64 da sessão e salva em session_b64.txt
Abra esse arquivo, selecione tudo e copie para o GitHub Secret.
"""
import base64

with open("session-accountverificarseguidor", "rb") as f:
    data = f.read()

b64 = base64.b64encode(data).decode("ascii")

with open("session_b64.txt", "w", encoding="ascii") as f:
    f.write(b64)

print(f"Salvo em session_b64.txt ({len(b64)} caracteres)")
print("Abra o arquivo no Notepad, Ctrl+A, Ctrl+C e cole no GitHub Secret.")
