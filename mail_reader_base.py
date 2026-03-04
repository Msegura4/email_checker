"""
mail_reader_base.py
Classe abstraite définissant l'interface commune pour tous les lecteurs de mail.
Chaque provider (Gmail, IMAP...) doit hériter de cette classe.
"""

from abc import ABC, abstractmethod


class BaseMailReader(ABC):
    """Interface commune pour lire des emails depuis n'importe quel provider."""

    @abstractmethod
    def fetch_unread_emails(self, max_results: int = 500, mark_as_read: bool = False) -> list[dict]:
        """
        Récupère les emails non lus.

        Retourne une liste de dicts avec les clés :
            - id       : identifiant unique du message (str)
            - sujet    : objet du mail (str)
            - corps    : corps texte du mail (str)
        """
        ...

    @abstractmethod
    def mark_as_read(self, mail_id: str) -> None:
        """Marque un mail comme lu via son identifiant."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Libère les ressources (connexion IMAP, session OAuth, etc.)."""
        ...

    # ── Context manager support ───────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
