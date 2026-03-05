"""
streamlit_app.py
Interface Streamlit pour l'agent de traitement de tickets email.
"""

import json
import os
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv, set_key
from streamlit_oauth import OAuth2Component

load_dotenv()


# ── Lecture des secrets (Streamlit Cloud > .env) ──────────────────────────────
def _secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


def _inject_secrets_to_env():
    for key in [
        "GROQ_KEY",
        "MAIL_PROVIDER",
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USER",
        "IMAP_PASSWORD",
        "IMAP_FOLDER",
        "IMAP_USE_SSL",
    ]:
        val = _secret(key)
        if val:
            os.environ[key] = val


_inject_secrets_to_env()

# ── Variables SSO au niveau MODULE ────────────────────────────────────────────
CLIENT_ID = _secret("GOOGLE_CLIENT_ID")
CLIENT_SECRET = _secret("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = _secret("REDIRECT_URI", "http://localhost:8501")

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES_SSO = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ══════════════════════════════════════════════════════════════════════════════
if "sso_token" not in st.session_state:
    st.session_state.sso_token = None
if "sso_user" not in st.session_state:
    st.session_state.sso_user = None

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title=(
        "Email Checker — Login"
        if st.session_state.sso_token is None
        else "Email Checker"
    ),
    page_icon="🔐" if st.session_state.sso_token is None else "🎫",
    layout="centered" if st.session_state.sso_token is None else "wide",
    initial_sidebar_state=(
        "collapsed" if st.session_state.sso_token is None else "expanded"
    ),
)


def _get_user_info(token: dict):
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo", headers=headers
    )
    return response.json() if response.status_code == 200 else None


def _build_gmail_service_from_sso():
    """Construit un service Gmail en forçant le token SSO comme valide."""
    import datetime
    from google.oauth2.credentials import Credentials as _GCreds
    from googleapiclient.discovery import build as _gbuild
    token = st.session_state.sso_token
    access_token = token.get("access_token")
    creds = _GCreds(
        token=access_token,
        refresh_token=token.get("refresh_token"),
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri=TOKEN_URL,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
    )
    # Forcer expiry dans le futur pour que creds.valid = True
    creds.expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    return _gbuild("gmail", "v1", credentials=creds)


def _debug_sso_token():
    token = st.session_state.sso_token or {}
    return {
        "has_access_token":  bool(token.get("access_token")),
        "has_refresh_token": bool(token.get("refresh_token")),
        "scopes":            token.get("scope", "non défini"),
        "token_type":        token.get("token_type", "?"),
    }


def _check_sso() -> bool:
    if st.session_state.sso_token is not None:
        return True

    st.markdown(
        """
    <div style='text-align:center; padding: 3rem 0 1rem 0;'>
        <h1>🔐 Email Checker</h1>
        <p style='color:#94a3b8;'>Connectez-vous avec votre compte Google</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if not CLIENT_ID or not CLIENT_SECRET:
            st.error(
                "❌ Configuration SSO manquante (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)."
            )
            return False

        oauth2 = OAuth2Component(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            authorize_endpoint=AUTHORIZATION_URL,
            token_endpoint=TOKEN_URL,
            refresh_token_endpoint=None,
            revoke_token_endpoint=None,
        )

        result = oauth2.authorize_button(
            name="🔑 Connexion avec Google",
            icon="https://www.google.com/favicon.ico",
            redirect_uri=REDIRECT_URI,
            scope=" ".join(SCOPES_SSO),
            key="google_oauth_main",
            extras_params={"prompt": "consent"},
        )

        if result and "token" in result:
            st.session_state.sso_token = result["token"]
            st.session_state.sso_user = _get_user_info(result["token"])
            st.rerun()

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Bouton IMAP qui déplie un formulaire
        if "show_imap_login" not in st.session_state:
            st.session_state.show_imap_login = False

        st.markdown("""
        <style>
        div[data-testid="stButton"] button[kind="secondary"] {
            height: 60px !important;
            font-size: 1.1rem !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
        }
        </style>
        """, unsafe_allow_html=True)
        if st.button("📬 Se connecter avec un autre compte mail (IMAP)", use_container_width=True, key="btn_imap_login"):
            st.session_state.show_imap_login = not st.session_state.show_imap_login
            st.rerun()

        if st.session_state.show_imap_login:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            with st.form("imap_login_form"):
                imap_host = st.text_input("Hôte IMAP", placeholder="imap.gmail.com")
                imap_port = st.text_input("Port", value="993")
                imap_user = st.text_input("Email", placeholder="vous@email.com")
                imap_pass = st.text_input("Mot de passe", type="password")
                imap_folder = st.text_input("Dossier", value="INBOX")
                imap_ssl = st.checkbox("SSL", value=True)
                submitted = st.form_submit_button("✅ Se connecter", type="primary", use_container_width=True)

            if submitted:
                if not all([imap_host, imap_user, imap_pass]):
                    st.error("Hôte, email et mot de passe sont requis.")
                else:
                    try:
                        import imaplib as _imap
                        _port = int(imap_port or 993)
                        _conn = _imap.IMAP4_SSL(imap_host, _port) if imap_ssl else _imap.IMAP4(imap_host, _port)
                        _conn.login(imap_user, imap_pass)
                        _conn.logout()
                        # Stocker config IMAP en session
                        from dotenv import set_key as _sk
                        if not ENV_FILE.exists():
                            ENV_FILE.touch()
                        _sk(str(ENV_FILE), "IMAP_HOST",     imap_host)
                        _sk(str(ENV_FILE), "IMAP_PORT",     str(imap_port))
                        _sk(str(ENV_FILE), "IMAP_USER",     imap_user)
                        _sk(str(ENV_FILE), "IMAP_PASSWORD", imap_pass)
                        _sk(str(ENV_FILE), "IMAP_FOLDER",   imap_folder)
                        _sk(str(ENV_FILE), "IMAP_USE_SSL",  "true" if imap_ssl else "false")
                        _sk(str(ENV_FILE), "MAIL_PROVIDER", "imap")
                        os.environ["IMAP_HOST"]     = imap_host
                        os.environ["IMAP_PORT"]     = str(imap_port)
                        os.environ["IMAP_USER"]     = imap_user
                        os.environ["IMAP_PASSWORD"] = imap_pass
                        os.environ["IMAP_FOLDER"]   = imap_folder
                        os.environ["IMAP_USE_SSL"]  = "true" if imap_ssl else "false"
                        os.environ["MAIL_PROVIDER"] = "imap"
                        # Créer un faux token SSO pour passer le _check_sso
                        st.session_state.sso_token = {"access_token": "imap", "imap": True}
                        st.session_state.sso_user  = {"name": imap_user, "email": imap_user}
                        st.session_state.show_imap_login = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Connexion IMAP échouée : {e}")

    return False


if not _check_sso():
    st.stop()


from profile_manager import (
    list_profiles,
    list_default_profiles,
    list_user_profiles,
    load_profile,
    save_profile,
    delete_profile,
    duplicate_profile,
    is_default_profile,
    slugify,
    build_context_txt,
    build_prompt_txt,
    get_category_to_sheet,
)

ENV_FILE = Path(".env")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _profile_label(p: dict) -> str:
    lock = " 🔒" if p.get("_is_default") else ""
    return f"{p.get('emoji','📁')} {p['nom']}{lock}"


def _reload_profiles():
    st.session_state.pop("profiles_cache", None)


def _get_profiles() -> list[dict]:
    if "profiles_cache" not in st.session_state:
        st.session_state.profiles_cache = list_profiles()
    return st.session_state.profiles_cache


def _nav(page_id: str):
    st.session_state.page = page_id
    st.rerun()


# ── Session state init ────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "lancer"
if "active_profile_idx" not in st.session_state:
    st.session_state.active_profile_idx = 0

page = st.session_state.page


# ── Modal : choisir un profil ─────────────────────────────────────────────────
@st.dialog("Choisir un profil", width="large")
def profile_picker():
    profiles_all = _get_profiles()

    st.markdown(
        """
    <style>
    .profile-card {
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
        cursor: pointer;
        transition: background 0.2s, border-color 0.2s;
        background: rgba(255,255,255,0.03);
        min-height: 90px;
    }
    .profile-card:hover {
        background: rgba(255,255,255,0.08);
        border-color: rgba(255,255,255,0.25);
    }
    .profile-card.active {
        border-color: #4f8ef7;
        background: rgba(79,142,247,0.08);
    }
    .profile-card-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .profile-card-desc {
        font-size: 0.82rem;
        color: #94a3b8;
        margin: 0;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    for i, p in enumerate(profiles_all):
        lock = " 🔒" if p.get("_is_default") else ""
        emoji = p.get("emoji", "📁")
        nom = p["nom"]
        desc = p.get("description", "")
        is_active = i == st.session_state.active_profile_idx
        active_class = "active" if is_active else ""
        active_badge = " ✅" if is_active else ""

        with cols[i % 2]:
            st.markdown(
                f"""<div class="profile-card {active_class}">
                    <div class="profile-card-title">{emoji} {nom}{lock}{active_badge}</div>
                    <p class="profile-card-desc">{desc}</p>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(
                "Sélectionner",
                key=f"pick_{i}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.active_profile_idx = i
                st.session_state.pop("profiles_cache", None)
                st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    """
<style>
div[data-testid="stSidebarNav"] { display: none; }
.nav-section { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
               letter-spacing: 0.08em; color: #94a3b8; margin: 1rem 0 0.3rem 0; }
div[data-testid="stSidebar"] button {
    width: 100%; text-align: left; background: transparent;
    border: none; border-radius: 6px; padding: 0.35rem 0.6rem;
    color: #e2e8f0; font-size: 0.9rem; cursor: pointer;
    transition: background 0.15s;
}
div[data-testid="stSidebar"] button:hover { background: rgba(255,255,255,0.08); }
</style>
""",
    unsafe_allow_html=True,
)

# ── Infos utilisateur SSO dans la sidebar ─────────────────────────────────────
if st.session_state.sso_user:
    with st.sidebar:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.image(st.session_state.sso_user.get("picture", ""), width=50)
        with col2:
            st.caption(f"**{st.session_state.sso_user.get('name')}**")
            st.caption(st.session_state.sso_user.get("email"))
        if st.button("🚪 Déconnexion"):
            st.session_state.sso_token = None
            st.session_state.sso_user = None
            st.rerun()
        st.divider()

# Profil actif
profiles = _get_profiles()
if st.session_state.active_profile_idx >= len(profiles):
    st.session_state.active_profile_idx = 0
active_profile = profiles[st.session_state.active_profile_idx] if profiles else None

st.sidebar.title("Bienvenu dans l'application Email Checker")
if active_profile:
    st.sidebar.markdown(
        f"<strong>Tri actif :<br>{active_profile.get('emoji','📁')} {active_profile['nom']}</strong>",
        unsafe_allow_html=True,
    )
if st.sidebar.button("↩ Changer de profil", key="btn_change_profile"):
    profile_picker()

st.sidebar.divider()

# ── Section 1 : Principal ─────────────────────────────────────────────────────
st.sidebar.markdown('<p class="nav-section">Principal</p>', unsafe_allow_html=True)
if st.sidebar.button("🚀 Lancer le tri", key="nav_lancer"):
    _nav("lancer")
if st.sidebar.button("📧 Compte connecté", key="nav_compte"):
    _nav("admin_mail")
if st.sidebar.button("🔄 Changer de compte mail", key="nav_changer_mail"):
    _nav("changer_compte")
if st.sidebar.button("🚪 Déconnecter son compte mail", key="nav_logout_mail"):
    st.session_state["sso_token"] = None
    st.session_state["sso_user"] = None
    st.rerun()

st.sidebar.divider()

# ── Section 2 : Gestion des profils ──────────────────────────────────────────
st.sidebar.markdown(
    '<p class="nav-section">Gestion des profils</p>', unsafe_allow_html=True
)
if st.sidebar.button("🔒 Tris par défaut", key="nav_defaut"):
    _nav("profils_defaut")
if st.sidebar.button("📋 Dupliquer un tri par défaut", key="nav_dupliquer"):
    _nav("profils_dupliquer")
if st.sidebar.button("➕ Créer un tri", key="nav_creer"):
    _nav("profils_creer")
if st.sidebar.button("✏️ Mes tris", key="nav_mes"):
    _nav("mes_profils")

st.sidebar.divider()

# ── Section 3 : Administration ────────────────────────────────────────────────
st.sidebar.markdown('<p class="nav-section">Administration</p>', unsafe_allow_html=True)
if st.sidebar.button("🔍 Diagnostic", key="nav_diag"):
    _nav("admin_diag")
if st.sidebar.button("🚧 Améliorations à venir", key="nav_roadmap"):
    _nav("roadmap")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Lancer le traitement
# ═════════════════════════════════════════════════════════════════════════════
if page == "lancer":
    st.title("🚀 Lancer le tri")
    if not active_profile:
        st.warning("Aucun tri disponible.")
        st.stop()

    st.divider()

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        max_emails = st.number_input(
            "Nombre max d'emails", min_value=1, max_value=1000, value=50
        )
    with col_b:
        mark_as_read = st.toggle("Marquer comme lus après traitement", value=False)
    with col_c:
        delay = st.slider("Délai entre appels LLM (s)", 0.0, 3.0, 1.0, 0.1)

    st.divider()
    log_area = st.empty()

    if st.button("▶️ Démarrer", type="primary", use_container_width=True):
        Path("context.txt").write_text(
            build_context_txt(active_profile), encoding="utf-8"
        )
        Path("prompt.txt").write_text(
            build_prompt_txt(active_profile), encoding="utf-8"
        )

        logs = []
        _start_time = time.time()

        def add_log(msg):
            logs.append(msg)
            elapsed = time.time() - _start_time
            log_area.code("\n".join(logs) + f"\n\n⏱️ Temps écoulé : {elapsed:.1f}s", language=None)

        def _check_timeout(step_name, timeout=30):
            elapsed = time.time() - _start_time
            if elapsed > timeout:
                add_log(f"\n⏰ TIMEOUT après {elapsed:.1f}s — bloqué à : {step_name}")
                add_log("\n📋 RAPPORT :")
                add_log(f"  • Provider : {os.getenv('MAIL_PROVIDER', 'gmail').upper()}")
                add_log(f"  • Dernière étape : {step_name}")
                add_log(f"  • Durée : {elapsed:.1f}s")
                add_log("  • Cause probable : token SSO expiré, rate limit Gmail, ou connexion lente")
                st.error(f"⏰ Timeout après {elapsed:.1f}s à l'étape : {step_name}")
                st.stop()

        try:
                from agent_mail import classify_mail

                provider = os.getenv("MAIL_PROVIDER", "gmail").lower()
                if provider == "gmail":
                    from mail_reader_gmail import GmailReader
                    from mail_reader_base import BaseMailReader

                    # Reader Gmail utilisant directement le service SSO — sans token.json
                    class GmailReaderSSO(BaseMailReader):
                        def __init__(self, service):
                            self.service = service

                        def fetch_unread_emails(self, max_results=500, mark_as_read=False):
                            tickets, page_token = [], None
                            while len(tickets) < max_results:
                                remaining = max_results - len(tickets)
                                batch_size = min(100, remaining)
                                params = {"userId": "me", "q": "is:unread",
                                          "maxResults": batch_size, "labelIds": ["INBOX"]}
                                if page_token:
                                    params["pageToken"] = page_token
                                resp = self.service.users().messages().list(**params).execute()
                                messages = resp.get("messages", [])
                                if not messages:
                                    break
                                for msg_ref in messages:
                                    if len(tickets) >= max_results:
                                        break
                                    mid = msg_ref["id"]
                                    try:
                                        time.sleep(0.1)
                                        msg = self.service.users().messages().get(
                                            userId="me", id=mid, format="full").execute()
                                        headers = msg.get("payload", {}).get("headers", [])
                                        sujet = next(
                                            (h["value"] for h in headers if h["name"].lower() == "subject"),
                                            "(Sans sujet)")
                                        corps = GmailReader._extract_body(GmailReader, msg.get("payload", {}))
                                        tickets.append({"id": mid, "sujet": sujet, "corps": corps})
                                        if mark_as_read:
                                            self.mark_as_read(mid)
                                    except Exception:
                                        pass
                                page_token = resp.get("nextPageToken")
                                if not page_token:
                                    break
                            return tickets

                        def mark_as_read(self, mail_id):
                            self.service.users().messages().modify(
                                userId="me", id=mail_id,
                                body={"removeLabelIds": ["UNREAD"]}).execute()

                        def close(self):
                            pass

                    sso_service = _build_gmail_service_from_sso()
                    MailReader = lambda: GmailReaderSSO(sso_service)
                else:
                    from mail_reader_imap import IMAPReader as MailReader

                add_log(f"[INFO] Profil : {active_profile['nom']}")
                add_log(f"[INFO] Provider : {provider.upper()}")
                if provider == "gmail":
                    _dbg = _debug_sso_token()
                    add_log(f"[DEBUG] access_token : {'✅' if _dbg['has_access_token'] else '❌'}")
                    add_log(f"[DEBUG] refresh_token : {'✅' if _dbg['has_refresh_token'] else '❌'}")
                    add_log(f"[DEBUG] scopes : {_dbg['scopes']}")
                add_log("[INFO] Connexion au provider mail...")

                category_to_sheet = get_category_to_sheet(active_profile)

                _check_timeout("Initialisation reader")
                try:
                    reader = MailReader()
                except Exception as e:
                    add_log(f"❌ Impossible de créer le reader : {e}")
                    st.error(f"Erreur connexion mail : {e}")
                    st.stop()

                _check_timeout("Connexion provider mail")
                with reader:
                    add_log(f"[INFO] Récupération des emails (max {max_emails})...")

                    # Fetch dans un thread avec timeout de 30s
                    import threading
                    _result_holder = {"tickets": None, "error": None, "step": "démarrage"}
                    def _fetch():
                        try:
                            _result_holder["step"] = "récupération emails"
                            _result_holder["tickets"] = reader.fetch_unread_emails(
                                max_results=max_emails, mark_as_read=False
                            )
                            _result_holder["step"] = "terminé"
                        except Exception as e:
                            _result_holder["error"] = e
                            _result_holder["step"] = f"erreur : {e}"

                    _thread = threading.Thread(target=_fetch)
                    _thread.start()
                    _waited = 0
                    while _thread.is_alive():
                        time.sleep(1)
                        _waited += 1
                        _step = _result_holder.get("step", "?")
                        add_log(f"[INFO] ({_waited}s) étape : {_step}")
                        if _waited >= 30:
                            _step = _result_holder.get("step", "?")
                            add_log("\n⏰ TIMEOUT — fetch_unread_emails bloqué après 30s")
                            add_log("📋 RAPPORT :")
                            add_log(f"  • Provider : {provider.upper()}")
                            add_log(f"  • Bloqué à : {_step}")
                            add_log("  • Solution : cliquez sur 'Se reconnecter' ci-dessous")
                            st.error(f"⏰ Timeout — bloqué à : {_step}")
                            if st.button("🔄 Se reconnecter avec les bons accès", type="primary"):
                                st.session_state.pop("sso_token", None)
                                st.session_state.pop("sso_user", None)
                                st.rerun()
                            st.stop()

                    if _result_holder["error"]:
                        add_log(f"❌ Erreur fetch : {_result_holder['error']}")
                        st.error(f"Erreur récupération emails : {_result_holder['error']}")
                        st.stop()

                    tickets = _result_holder["tickets"] or []
                    add_log(f"[INFO] {len(tickets)} emails récupérés.")

                    if not tickets:
                        add_log("[OK] Aucun email non lu à traiter.")
                        st.success("Aucun email non lu.")
                        st.stop()

                    results = []
                    success, errors = 0, 0

                    for i, ticket in enumerate(tickets, 1):
                        sujet = ticket.get("sujet", "(Sans sujet)")
                        corps = ticket.get("corps", "")
                        mail_id = ticket.get("id")
                        add_log(f"[{i}/{len(tickets)}] {sujet[:60]}...")

                        try:
                            # Retry automatique si rate limit Groq
                            for _attempt in range(3):
                                try:
                                    result = classify_mail(f"Sujet : {sujet}\n\n{corps}")
                                    break
                                except Exception as _e:
                                    if _attempt < 2:
                                        add_log(f"  ⚠️ Groq rate limit, retry {_attempt+1}/3...")
                                        time.sleep(3)
                                    else:
                                        raise _e
                            categorie = result.get("categorie", "")
                            urgence = result.get("urgence", "")
                            resume = result.get("résumé", sujet)
                            results.append(
                                {
                                    "Sujet": sujet,
                                    "Catégorie": categorie,
                                    "Urgence": urgence,
                                    "Synthèse": resume,
                                    "Corps": corps,
                                    "_mail_id": mail_id,
                                }
                            )
                            if mark_as_read:
                                reader.mark_as_read(mail_id)
                            add_log(f"  → {categorie} | {urgence}")
                            success += 1
                        except Exception as e:
                            add_log(f"  ❌ Erreur : {e}")
                            errors += 1

                        if i < len(tickets):
                            time.sleep(delay)

                st.session_state["last_results"] = results
                add_log(f"\n✅ Terminé — {success} succès, {errors} erreurs.")

                if errors == 0:
                    st.success(f"✅ {success} emails traités avec succès !")
                else:
                    st.warning(f"⚠️ {success} succès, {errors} erreurs.")

        except Exception as e:
            add_log(f"\n❌ Erreur fatale : {e}")
            st.error(f"Erreur : {e}")

    # ── Résultats ─────────────────────────────────────────────────────────────
    if "last_results" in st.session_state and st.session_state["last_results"]:
        import pandas as pd

        st.divider()
        results = st.session_state["last_results"]

        if "mail_actions" not in st.session_state:
            st.session_state.mail_actions = {}

        actifs = [
            r
            for i, r in enumerate(results)
            if st.session_state.mail_actions.get(i) != "supprimer"
        ]
        conserves = sum(
            1 for v in st.session_state.mail_actions.values() if v == "conserver"
        )
        supprimes = sum(
            1 for v in st.session_state.mail_actions.values() if v == "supprimer"
        )

        col_title, col_stats = st.columns([3, 2])
        with col_title:
            st.markdown(f"### 📋 Résultats — {len(actifs)} emails")
        with col_stats:
            st.caption(f"✅ {conserves} à conserver · 🗑️ {supprimes} à supprimer")

        @st.dialog("📧 Contenu de l'email", width="large")
        def show_email(idx):
            import re
            mail = results[idx]

            st.markdown("""
            <style>
            div[role="dialog"] { background-color: #0f1117 !important; }
            div[role="dialog"] p, div[role="dialog"] span,
            div[role="dialog"] label { color: #e2e8f0 !important; }
            div[role="dialog"] hr { border-color: rgba(255,255,255,0.1) !important; }
            </style>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style='background:#1e2130; border:1px solid rgba(255,255,255,0.08);
                        border-radius:10px; padding:16px 20px; margin-bottom:12px;'>
                <div style='font-size:1rem; font-weight:600; color:#f1f5f9; margin-bottom:10px;'>{mail['Sujet']}</div>
                <div style='display:flex; gap:10px; flex-wrap:wrap;'>
                    <span style='background:#2d3748; color:#94a3b8; font-size:0.78rem; padding:3px 10px; border-radius:20px;'>📂 {mail['Catégorie']}</span>
                    <span style='background:#2d3748; color:#f59e0b; font-size:0.78rem; padding:3px 10px; border-radius:20px;'>🚨 {mail['Urgence']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style='background:#1a2035; border-left:3px solid #4f8ef7;
                        border-radius:0 8px 8px 0; padding:12px 16px; margin-bottom:16px;
                        color:#cbd5e1; font-size:0.9rem; line-height:1.6;'>
                💡 <strong style='color:#93c5fd;'>Synthèse :</strong> {mail["Synthèse"]}
            </div>
            """, unsafe_allow_html=True)

            corps = mail.get("Corps", "(Corps non disponible)")
            corps = re.sub(r"<style[^>]*>.*?</style>", " ", corps, flags=re.DOTALL)
            corps = re.sub(r"<script[^>]*>.*?</script>", " ", corps, flags=re.DOTALL)
            corps = re.sub(r"<[^>]+>", " ", corps)
            corps = re.sub(r"&nbsp;", " ", corps)
            corps = re.sub(r"&amp;", "&", corps)
            corps = re.sub(r"&lt;", "<", corps)
            corps = re.sub(r"&gt;", ">", corps)
            corps = re.sub(r"[ \t]{2,}", " ", corps)
            corps = re.sub(r"\n{3,}", "\n\n", corps).strip()

            st.markdown(
                f"<div style='background:#0f1117; border:1px solid rgba(255,255,255,0.08);"
                f"border-radius:8px; padding:16px; font-size:0.85rem; line-height:1.7;"
                f"white-space:pre-wrap; color:#cbd5e1; max-height:380px; overflow-y:auto;'>"
                f"{corps}</div>",
                unsafe_allow_html=True,
            )

        def trash_on_gmail(mail_ids: list) -> tuple[int, int]:
            provider = os.getenv("MAIL_PROVIDER", "gmail").lower()
            ok, fail = 0, 0
            if provider == "gmail":
                try:
                    _svc = _build_gmail_service_from_sso()
                    for mid in mail_ids:
                        if mid:
                            try:
                                _svc.users().messages().trash(
                                    userId="me", id=mid
                                ).execute()
                                ok += 1
                            except Exception:
                                fail += 1
                except Exception:
                    fail += len(mail_ids)
            return ok, fail

        urgency_order = {
            u["label"]: i for i, u in enumerate(active_profile.get("urgences", []))
        }
        sorted_results = sorted(
            enumerate(results), key=lambda x: urgency_order.get(x[1]["Urgence"], 99)
        )

        categories = [c["label"] for c in active_profile.get("categories", [])]
        tab_labels = []
        for cat in categories:
            count = sum(
                1
                for _, r in sorted_results
                if r["Catégorie"] == cat
                and st.session_state.mail_actions.get(_) != "supprimer"
            )
            tab_labels.append(f"{cat} ({count})")

        tabs = st.tabs(tab_labels)
        for tab, cat in zip(tabs, categories):
            with tab:
                cat_results = [
                    (gi, r)
                    for gi, r in sorted_results
                    if r["Catégorie"] == cat
                    and st.session_state.mail_actions.get(gi) != "supprimer"
                ]
                if not cat_results:
                    st.caption("Aucun email dans cette catégorie.")
                else:
                    h1, h2, h3, h4, h5 = st.columns([0.5, 5, 2, 1, 1])
                    with h1:
                        st.caption("☑")
                    with h2:
                        st.caption("Sujet")
                    with h3:
                        st.caption("Urgence")
                    with h4:
                        st.caption("")
                    with h5:
                        st.caption("")

                    for gi, mail in cat_results:
                        action = st.session_state.mail_actions.get(gi)
                        is_kept = action == "conserver"

                        col_chk, col_sujet, col_urg, col_view, col_act = st.columns(
                            [0.5, 5, 2, 1, 1]
                        )

                        with col_chk:
                            checked = st.checkbox(
                                "",
                                key=f"chk_{gi}",
                                value=is_kept,
                                label_visibility="collapsed",
                            )

                        with col_sujet:
                            style = "color:#4ade80;" if is_kept else ""
                            st.markdown(
                                f"<span style='font-size:0.9rem;{style}'>{mail['Sujet'][:75]}</span>",
                                unsafe_allow_html=True,
                            )

                        with col_urg:
                            st.caption(mail["Urgence"])

                        with col_view:
                            if st.button("👁️", key=f"view_{gi}", help="Voir l'email"):
                                show_email(gi)

                        with col_act:
                            if checked and not is_kept:
                                st.session_state.mail_actions[gi] = "conserver"
                                st.rerun()
                            elif not checked and is_kept:
                                st.session_state.mail_actions[gi] = None
                                st.rerun()

                    selected = [
                        gi
                        for gi, _ in cat_results
                        if st.session_state.mail_actions.get(gi) == "conserver"
                    ]
                    if selected:
                        st.markdown("")
                        col_del, col_reset = st.columns([1, 1])
                        with col_del:
                            if st.button(
                                f"🗑️ Supprimer la sélection ({len(selected)})",
                                key=f"del_{cat}",
                                type="secondary",
                            ):
                                mail_ids = [
                                    results[gi].get("_mail_id") for gi in selected
                                ]
                                ok, fail = trash_on_gmail(mail_ids)
                                for gi in selected:
                                    st.session_state.mail_actions[gi] = "supprimer"
                                if ok:
                                    st.success(
                                        f"✅ {ok} email(s) mis à la corbeille sur Gmail."
                                    )
                                if fail:
                                    st.warning(
                                        f"⚠️ {fail} email(s) non supprimés (IMAP ou erreur)."
                                    )
                                st.rerun()
                        with col_reset:
                            if st.button(
                                "↩️ Désélectionner", key=f"reset_{cat}", type="secondary"
                            ):
                                for gi in selected:
                                    st.session_state.mail_actions[gi] = None
                                st.rerun()

        st.divider()
        col_csv, col_clear = st.columns([2, 1])
        with col_csv:
            df_export = pd.DataFrame(
                [
                    {k: v for k, v in r.items() if k != "Corps"}
                    for i, r in enumerate(results)
                    if st.session_state.mail_actions.get(i) != "supprimer"
                ]
            )
            csv = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Exporter en CSV",
                data=csv,
                file_name=f"resultats_{active_profile['id']}.csv",
                mime="text/csv",
                type="primary",
            )
        with col_clear:
            if st.button("🔄 Réinitialiser les actions", type="secondary"):
                st.session_state.mail_actions = {}
                st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Profils par défaut
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_defaut":
    st.title("🔒 Tris par défaut")

    st.markdown(
        """
    <style>
    details[open] > summary {
        background-color: #fef2f2 !important;
        border-left: 4px solid #f87171 !important;
        border-radius: 0 6px 6px 0;
        padding-left: 1rem !important;
    }
    details[open] > summary p { color: #b91c1c !important; font-weight: 600; }
    details[open] > summary svg { fill: #ef4444 !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    default_profiles = list_default_profiles()
    if not default_profiles:
        st.info("Aucun profil par défaut trouvé dans profiles/defaults/.")
    else:
        st.info(
            "Ces propositions de tris sont fournis avec l'application et ne peuvent pas être modifiés. "
            "Dépliez-les pour voir leur contenu complet, et **dupliquez-les** pour créer votre propre version."
        )
        st.divider()

        for p in default_profiles:
            pid = p["id"]
            pcats = p.get("categories", [])
            purgs = p.get("urgences", [])

            with st.expander(
                f"{p.get('emoji','📁')} **{p['nom']}**  🔒", expanded=False
            ):
                st.markdown(f"_{p.get('description', '')}_")
                st.divider()

                st.markdown("**📂 Catégories**")
                for cat in pcats:
                    col_lbl, col_dsc = st.columns([1, 2])
                    with col_lbl:
                        st.markdown(f"**`{cat['label']}`**")
                    with col_dsc:
                        st.markdown(
                            f"<span style='color:#555'>{cat.get('description','')}</span>",
                            unsafe_allow_html=True,
                        )

                st.divider()

                st.markdown("**🚨 Niveaux d'urgence**")
                for urg in purgs:
                    col_lbl, col_dsc = st.columns([1, 2])
                    with col_lbl:
                        st.markdown(f"**`{urg['label']}`**")
                    with col_dsc:
                        st.markdown(
                            f"<span style='color:#555'>{urg.get('description','')}</span>",
                            unsafe_allow_html=True,
                        )

                st.divider()

                st.markdown("**📝 Contexte & Prompt LLM**")
                st.markdown("**Contexte**")
                st.code(p.get("context", ""), language=None)
                st.markdown("**Prompt de base**")
                st.code(p.get("prompt", ""), language=None)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Créer depuis un défaut
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_dupliquer":
    st.title("📋 Créer à partir d'un tri par défaut")

    default_profiles = list_default_profiles()
    if not default_profiles:
        st.info("Aucun tri par défaut disponible.")
    else:
        st.info(
            "Choisissez un tri par défaut comme point de départ, donnez-lui un nouveau nom, puis personnalisez-le dans **✏️ Mes tris**."
        )
        st.divider()

        default_ids = [p["id"] for p in default_profiles]
        source_id = st.selectbox(
            "Tri source",
            default_ids,
            format_func=lambda pid: next(
                (
                    f"{p.get('emoji','📁')} {p['nom']}"
                    for p in default_profiles
                    if p["id"] == pid
                ),
                pid,
            ),
        )
        source = next((p for p in default_profiles if p["id"] == source_id), None)

        new_name = st.text_input(
            "Nom du nouveau tri",
            value=f"{source['nom']} (copie)" if source else "",
            placeholder="ex : Support IT — Équipe Lyon",
        )

        if st.button("📋 Créer ce profil", type="primary", use_container_width=True):
            if not new_name.strip():
                st.error("Le nom ne peut pas être vide.")
            else:
                try:
                    new_p = duplicate_profile(source_id, new_name.strip())
                    _reload_profiles()
                    st.success(
                        f"✅ Profil **'{new_p['nom']}'** créé ! Rendez-vous dans **✏️ Mes profils** pour le modifier."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Créer un profil from scratch
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_creer":
    st.title("➕ Créer un tri")

    with st.form("new_profile"):
        col1, col2 = st.columns([3, 1])
        with col1:
            nom = st.text_input("Nom du nouveau tri *", placeholder="ex: Chargé RH")
        with col2:
            emoji = st.text_input("Emoji", value="📁", max_chars=2)
        desc = st.text_area("Description", height=80)
        context = st.text_area(
            "Contexte LLM", height=100, placeholder="Les emails proviennent de..."
        )
        prompt = st.text_area(
            "Prompt de base",
            height=100,
            placeholder="Tu es un agent spécialisé dans...",
        )

        st.subheader("Catégories (min. 2)")
        cats = []
        for j in range(5):
            c1, c2 = st.columns([2, 4])
            with c1:
                lbl = st.text_input(f"Catégorie {j+1}", key=f"new_cat_{j}")
            with c2:
                dsc = st.text_input(
                    "Description", key=f"new_cat_dsc_{j}", label_visibility="collapsed"
                )
            if lbl:
                cats.append({"id": slugify(lbl), "label": lbl, "description": dsc})

        st.subheader("Urgences")
        use_default_urgences = st.checkbox(
            "Utiliser les urgences standard (Critique → Anodine)", value=True
        )

        submitted = st.form_submit_button("✅ Créer le profil", type="primary")

    if submitted:
        if not nom:
            st.error("Le nom est obligatoire.")
        elif len(cats) < 2:
            st.error("Ajoutez au moins 2 catégories.")
        else:
            default_urgences = [
                {
                    "label": "Critique",
                    "description": "Impact majeur, opération impossible.",
                },
                {
                    "label": "Élevée",
                    "description": "Forte gêne, traitement prioritaire.",
                },
                {"label": "Modérée", "description": "Gêne notable mais non bloquante."},
                {"label": "Faible", "description": "Problème mineur."},
                {
                    "label": "Anodine",
                    "description": "Demande simple, aucun enjeu d'urgence.",
                },
            ]
            new_profile = {
                "id": slugify(nom),
                "nom": nom,
                "emoji": emoji,
                "description": desc,
                "context": context,
                "prompt": prompt,
                "categories": cats,
                "urgences": default_urgences if use_default_urgences else [],
            }
            try:
                save_profile(new_profile)
                _reload_profiles()
                st.success(f"✅ Profil '{nom}' créé !")
                st.rerun()
            except Exception as e:
                st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Mes profils
# ═════════════════════════════════════════════════════════════════════════════
elif page == "mes_profils":
    st.title("✏️ Mes profils")

    st.markdown(
        """
    <style>
    details[open] > summary {
        background-color: #fef2f2 !important;
        border-left: 4px solid #f87171 !important;
        border-radius: 0 6px 6px 0;
        padding-left: 1rem !important;
    }
    details[open] > summary p { color: #b91c1c !important; font-weight: 600; }
    details[open] > summary svg { fill: #ef4444 !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    user_profiles = list_user_profiles()

    if not user_profiles:
        st.info(
            "Vous n'avez pas encore de tri personnalisé. "
            "Dupliquez un profil par défaut ou créez-en un depuis les boutons dédiés"
        )
    else:
        st.caption(
            "Dépliez un profil pour le modifier. La suppression est disponible en bas de chaque fiche."
        )
        st.divider()

        for p in user_profiles:
            pid = p["id"]
            pcats = p.get("categories", [])
            purgs = p.get("urgences", [])

            with st.expander(f"{p.get('emoji','📁')} **{p['nom']}**", expanded=False):

                with st.form(f"edit_{pid}"):
                    st.markdown("**Informations générales**")
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        new_nom = st.text_input("Nom", value=p["nom"], key=f"nom_{pid}")
                    with col2:
                        new_emoji = st.text_input(
                            "Emoji",
                            value=p.get("emoji", "📁"),
                            max_chars=2,
                            key=f"emoji_{pid}",
                        )
                    new_desc = st.text_area(
                        "Description",
                        value=p.get("description", ""),
                        height=68,
                        key=f"desc_{pid}",
                    )

                    st.divider()

                    st.markdown("**📝 Contexte & Prompt LLM**")
                    new_context = st.text_area(
                        "Contexte",
                        value=p.get("context", ""),
                        height=110,
                        key=f"ctx_{pid}",
                    )
                    new_prompt = st.text_area(
                        "Prompt de base",
                        value=p.get("prompt", ""),
                        height=110,
                        key=f"prompt_{pid}",
                    )

                    st.divider()

                    st.markdown("**📂 Catégories**")
                    new_cats = []
                    for j, cat in enumerate(pcats):
                        c1, c2, c3 = st.columns([2, 3, 0.7])
                        with c1:
                            lbl = st.text_input(
                                "Label",
                                value=cat["label"],
                                key=f"cat_lbl_{pid}_{j}",
                                label_visibility="collapsed",
                            )
                        with c2:
                            dsc = st.text_input(
                                "Description",
                                value=cat.get("description", ""),
                                key=f"cat_dsc_{pid}_{j}",
                                label_visibility="collapsed",
                            )
                        with c3:
                            keep = st.checkbox(
                                "✓",
                                value=True,
                                key=f"cat_keep_{pid}_{j}",
                                help="Décocher pour supprimer",
                            )
                        if keep and lbl:
                            new_cats.append(
                                {"id": slugify(lbl), "label": lbl, "description": dsc}
                            )

                    st.caption("Nouvelle catégorie")
                    na1, na2 = st.columns([2, 3])
                    with na1:
                        add_lbl = st.text_input(
                            "Label",
                            key=f"add_cat_lbl_{pid}",
                            placeholder="Label...",
                            label_visibility="collapsed",
                        )
                    with na2:
                        add_dsc = st.text_input(
                            "Description",
                            key=f"add_cat_dsc_{pid}",
                            placeholder="Description...",
                            label_visibility="collapsed",
                        )
                    if add_lbl:
                        new_cats.append(
                            {
                                "id": slugify(add_lbl),
                                "label": add_lbl,
                                "description": add_dsc,
                            }
                        )

                    st.divider()

                    st.markdown("**🚨 Niveaux d'urgence**")
                    new_urgences = []
                    for k, urg in enumerate(purgs):
                        u1, u2 = st.columns([1, 3])
                        with u1:
                            ulbl = st.text_input(
                                "Niveau",
                                value=urg["label"],
                                key=f"urg_lbl_{pid}_{k}",
                                label_visibility="collapsed",
                            )
                        with u2:
                            udsc = st.text_input(
                                "Description",
                                value=urg.get("description", ""),
                                key=f"urg_dsc_{pid}_{k}",
                                label_visibility="collapsed",
                            )
                        if ulbl:
                            new_urgences.append({"label": ulbl, "description": udsc})

                    st.divider()
                    saved = st.form_submit_button(
                        "💾 Enregistrer les modifications",
                        type="primary",
                        use_container_width=True,
                    )

                if saved:
                    updated = {
                        "id": pid,
                        "nom": new_nom,
                        "emoji": new_emoji,
                        "description": new_desc,
                        "context": new_context,
                        "prompt": new_prompt,
                        "categories": new_cats,
                        "urgences": new_urgences,
                    }
                    try:
                        save_profile(updated)
                        _reload_profiles()
                        st.success("✅ Profil enregistré !")
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))

                st.markdown(
                    "<div style='margin-top: 8px'></div>", unsafe_allow_html=True
                )
                col_spacer, col_del = st.columns([3, 1])
                with col_del:
                    if st.button(
                        "🗑️ Supprimer ce profil",
                        key=f"del_{pid}",
                        use_container_width=True,
                    ):
                        try:
                            delete_profile(pid)
                            _reload_profiles()
                            st.warning(f"Profil '{p['nom']}' supprimé.")
                            st.rerun()
                        except PermissionError as e:
                            st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Compte connecté
# ═════════════════════════════════════════════════════════════════════════════
elif page == "admin_mail":
    st.title("📧 Compte connecté")
    current_provider = os.getenv("MAIL_PROVIDER", "gmail")
    if current_provider == "gmail":
        try:
            _svc       = _build_gmail_service_from_sso()
            _profile   = _svc.users().getProfile(userId="me").execute()
            _email     = _profile.get("emailAddress", "inconnu")
            _n_msgs    = _profile.get("messagesTotal", "?")
            _n_threads = _profile.get("threadsTotal", "?")

            st.success(f"✅ Connecté en tant que **{_email}**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Messages totaux", f"{_n_msgs:,}" if isinstance(_n_msgs, int) else _n_msgs)
            with col2:
                st.metric("Fils de discussion", f"{_n_threads:,}" if isinstance(_n_threads, int) else _n_threads)
        except Exception as e:
            st.error(f"❌ Impossible de lire le compte : {e}")
    else:
        imap_user = os.getenv("IMAP_USER", "")
        imap_host = os.getenv("IMAP_HOST", "")
        if imap_user and imap_host:
            st.success(f"✅ Connecté via IMAP : **{imap_user}** @ {imap_host}")
        else:
            st.warning("⚠️ Aucun compte IMAP configuré.")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Changer de compte mail
# ═════════════════════════════════════════════════════════════════════════════
elif page == "changer_compte":
    st.title("🔄 Changer de compte mail")
    st.divider()

    new_provider = st.radio(
        "Choisir le type de compte mail",
        [None, "gmail", "imap"],
        index=0,
        format_func=lambda x: "— Sélectionner —" if x is None else (
            "📧 Gmail (OAuth2)" if x == "gmail" else "📬 IMAP (Thunderbird, Outlook...)"
        ),
        horizontal=True,
    )

    if new_provider == "gmail":
        st.session_state["sso_token"] = None
        st.session_state["sso_user"] = None
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        set_key(str(ENV_FILE), "MAIL_PROVIDER", "gmail")
        os.environ["MAIL_PROVIDER"] = "gmail"
        st.rerun()

    elif new_provider == "imap":
        st.divider()
        with st.form("imap_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                imap_host = st.text_input("Hôte IMAP", value=os.getenv("IMAP_HOST", ""), placeholder="imap.gmail.com")
            with col2:
                imap_port = st.text_input("Port", value=os.getenv("IMAP_PORT", "993"))
            imap_user   = st.text_input("Email",        value=os.getenv("IMAP_USER",     ""))
            imap_pass   = st.text_input("Mot de passe", value=os.getenv("IMAP_PASSWORD", ""), type="password")
            imap_folder = st.text_input("Dossier",      value=os.getenv("IMAP_FOLDER",   "INBOX"))
            imap_ssl    = st.checkbox("SSL", value=os.getenv("IMAP_USE_SSL", "true") == "true")
            save_imap   = st.form_submit_button("💾 Sauvegarder la config IMAP", type="primary")

        if save_imap:
            if not ENV_FILE.exists():
                ENV_FILE.touch()
            set_key(str(ENV_FILE), "IMAP_HOST",     imap_host)
            set_key(str(ENV_FILE), "IMAP_PORT",     str(imap_port))
            set_key(str(ENV_FILE), "IMAP_USER",     imap_user)
            set_key(str(ENV_FILE), "IMAP_PASSWORD", imap_pass)
            set_key(str(ENV_FILE), "IMAP_FOLDER",   imap_folder)
            set_key(str(ENV_FILE), "IMAP_USE_SSL",  "true" if imap_ssl else "false")
            set_key(str(ENV_FILE), "MAIL_PROVIDER", "imap")
            os.environ["MAIL_PROVIDER"] = "imap"
            st.success("✅ Config IMAP sauvegardée.")

        st.divider()
        st.markdown("**Hôtes IMAP courants**")
        st.table({
            "Service":   ["Gmail", "Outlook", "Yahoo", "OVH"],
            "IMAP_HOST": ["imap.gmail.com", "outlook.office365.com", "imap.mail.yahoo.com", "ssl0.ovh.net"],
            "Port":      ["993", "993", "993", "993"],
        })

# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Diagnostic
# ═════════════════════════════════════════════════════════════════════════════
elif page == "admin_diag":
    st.title("🔍 Diagnostic")
    st.caption("Vérification de l'état de toutes les connexions et dépendances.")

    if st.button("🔄 Lancer les vérifications", type="primary"):
        st.session_state["run_diag"] = True

    if st.session_state.get("run_diag"):
        st.divider()

        st.subheader("📁 Fichiers")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "credentials.json",
                "✅ Présent" if Path("credentials.json").exists() else "❌ Absent",
            )
        with col2:
            st.metric(
                "SSO Google",
                "✅ Connecté" if st.session_state.sso_token else "❌ Non connecté",
            )

        st.divider()

        st.subheader("⚙️ Variables d'environnement")
        st.metric("MAIL_PROVIDER", os.getenv("MAIL_PROVIDER", "gmail").upper())

        st.divider()

        st.subheader("🤖 API Groq")
        groq_key = os.getenv("GROQ_KEY", "")
        if not groq_key:
            st.error("❌ Clé Groq non configurée côté serveur.")
        else:
            with st.spinner("Test Groq..."):
                try:
                    from groq import Groq

                    _client = Groq(api_key=groq_key)
                    _client.chat.completions.create(
                        messages=[{"role": "user", "content": "OK"}],
                        model="llama-3.3-70b-versatile",
                        max_tokens=5,
                    )
                    st.success(
                        "✅ Groq opérationnel — modèle : `llama-3.3-70b-versatile`"
                    )
                except Exception as e:
                    st.error(f"❌ Groq inaccessible : {e}")

        st.divider()

        st.subheader("📧 Compte Gmail")
        with st.spinner("Connexion Gmail..."):
            try:
                _svc = _build_gmail_service_from_sso()
                _profile = _svc.users().getProfile(userId="me").execute()
                _email = _profile.get("emailAddress", "inconnu")
                _n_msgs = _profile.get("messagesTotal", "?")
                st.success(
                    f"✅ Connecté : **{_email}** ({_n_msgs:,} messages)"
                    if isinstance(_n_msgs, int)
                    else f"✅ Connecté : **{_email}**"
                )
            except Exception as e:
                st.error(f"❌ Gmail inaccessible : {e}")

        st.divider()

        if os.getenv("MAIL_PROVIDER", "gmail") == "imap":
            st.subheader("📬 Connexion IMAP")
            imap_host = os.getenv("IMAP_HOST", "")
            imap_user = os.getenv("IMAP_USER", "")
            imap_pass = os.getenv("IMAP_PASSWORD", "")
            if not all([imap_host, imap_user, imap_pass]):
                st.error("❌ Variables IMAP incomplètes.")
            else:
                with st.spinner(f"Connexion IMAP à {imap_host}..."):
                    try:
                        import imaplib

                        _port = int(os.getenv("IMAP_PORT", 993))
                        _use_ssl = os.getenv("IMAP_USE_SSL", "true").lower() != "false"
                        _conn = (
                            imaplib.IMAP4_SSL(imap_host, _port)
                            if _use_ssl
                            else imaplib.IMAP4(imap_host, _port)
                        )
                        _conn.login(imap_user, imap_pass)
                        _conn.logout()
                        st.success(f"✅ IMAP connecté : **{imap_user}** @ {imap_host}")
                    except Exception as e:
                        st.error(f"❌ IMAP inaccessible : {e}")

        st.divider()

        st.subheader("🗂️ Profils chargés")
        _all_profiles = _get_profiles()
        _defaults = [p for p in _all_profiles if p.get("_is_default")]
        _users = [p for p in _all_profiles if not p.get("_is_default")]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Profils par défaut", len(_defaults))
        with col2:
            st.metric("Profils personnalisés", len(_users))
        for p in _all_profiles:
            lock = " 🔒" if p.get("_is_default") else ""
            actif = (
                " ← **actif**"
                if active_profile and p.get("id") == active_profile.get("id")
                else ""
            )
            st.caption(f"{p.get('emoji','📁')} {p['nom']}{lock}{actif}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Améliorations à venir
# ═════════════════════════════════════════════════════════════════════════════
elif page == "roadmap":
    st.title("🚧 Améliorations à venir")
    st.caption("Idées et évolutions prévues pour les prochaines versions.")

    st.divider()

    st.subheader("Support multi-utilisateurs")
    st.markdown(
        """
L'architecture actuelle est pensée pour un usage **mono-utilisateur** (une machine, un compte Google).

Pour permettre à plusieurs utilisateurs d'utiliser l'application indépendamment, il faudrait :

- **Passer l'app Google Cloud en mode Production** — aujourd'hui seuls les emails ajoutés manuellement comme *testeurs* dans la Google Cloud Console peuvent s'authentifier. Un utilisateur inconnu reçoit une erreur `403 access_denied`.
- **Implémenter un OAuth2 web flow côté serveur** — chaque utilisateur aurait sa propre session et son propre `token.json`, géré dynamiquement plutôt que stocké sur le disque.
- **Isoler les configurations par utilisateur** — clé Groq, Google Sheet ID, profils actifs, chacun dans son propre espace.

En attendant, la solution la plus simple pour partager l'app est d'ajouter l'email de chaque utilisateur comme testeur dans la [Google Cloud Console](https://console.cloud.google.com).
    """
    )

    st.divider()

    st.subheader("Nouveau tri par défaut : Facturation")
    st.markdown(
        """
Un nouveau profil **Facturation** est prévu pour lire et trier automatiquement les emails contenant des factures.

**Catégories prévues :**
- `Facture reçue` — facture fournisseur à traiter ou à payer
- `Facture envoyée` — confirmation d'émission ou de paiement client
- `Relance paiement` — relance pour impayé, demande de régularisation
- `Avoir / Remboursement` — avoir commercial, note de crédit, remboursement
- `Abonnement / Récurrent` — renouvellement automatique, SaaS, abonnement mensuel
    """
    )

    st.divider()

    st.subheader("Ajout de la suppression avec une connexion IMAP")
    st.markdown(
        """
Actuellement l'application place dans la corbeille Gmail les éléments supprimés depuis le visualisateur, nous travaillons sur une fonctionnalité similaire avec les connexions IMAP.
    """
    )

    st.divider()

    st.subheader("Création d'un Google Sheet pour les connexions avec compte Google")
    st.markdown(
        """
Pour les connexions avec un compte Gmail, il sera possible de créer un Google Sheet pour les résultats de l'analyse automatiquement. L'export en CSV manuel restera disponible.
    """
    )

    st.divider()

    st.subheader("Modifications de nommage et d'organisation du menu")
    st.markdown(
        """
- Onglet API
- Détail du diagnostic
- Partie "Principal" du sidebar, changement de dénomination
- ...
    """
    )

    st.divider()
    st.info(
        "💡 D'autres idées ? N'hésitez pas à contribuer sur le dépôt GitHub ou simplement contacter les créateurs : Kémil Lamouri et Mathias Segura."
    )
