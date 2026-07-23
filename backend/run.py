"""Point d'entrée pour lancer le serveur du site MSolutions3D."""
import uvicorn

if __name__ == "__main__":
    # host 127.0.0.1 = accessible seulement depuis cette machine.
    # Pour exposer sur le réseau local, remplacer par "0.0.0.0".
    # server_header=False : ne pas divulguer « uvicorn » (l'en-tête Server est posé par l'app).
    # proxy_headers/forwarded : à activer derrière un reverse proxy en production pour que
    # l'IP réelle du client soit utilisée (rate-limit correct) — voir la doc d'hébergement.
    uvicorn.run("app:app", host="127.0.0.1", port=8123, reload=False, server_header=False)
