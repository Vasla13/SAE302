import time

print("Début de l'exécution...")

# Boucle qui attend 10 secondes entre chaque itération
for i in range(4):  # 4 itérations pour atteindre 40 secondes
    print(f"Étape {i + 1} : Attente de 10 secondes...")
    time.sleep(10)

print("Fin de l'exécution.")
