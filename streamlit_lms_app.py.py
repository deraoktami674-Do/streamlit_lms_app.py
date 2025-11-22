"""
Simple LMS single-file Streamlit app fulfilling the requested features:
- kode akses kelas (class access code)
- kode akses setiap materi (material access code)
- absen (attendance)
- fitur notifikasi (simple notification panel)
- akses via shared link (Streamlit app URL)
- upload PDF/flipbook/liveworksheets shown inline (no new tab)
- forum diskusi siswa
- upload video shown inline
- embed virtual laboratory (PhET or any iframe)
- pretest and postest creation + student attempts + auto-evaluation for MCQ

Notes / limitations:
- This is a single-file prototype intended to run with `streamlit run streamlit_lms_app.py`.
- Persistence uses SQLite (file: lms.db) in the working directory.
- "Real-time" notifications are simulated by checking the notifications table on each page reload.
  For push-style notifications you'd integrate with websockets (e.g., Streamlit-Server-Session + Redis) or an external push service.
- File uploads are stored in a local `uploads/` folder and served back as base64 embedded data for inline viewing.

"""

import streamlit as st
import sqlite3
import os
import hashlib
import base64
import uuid
from datetime import datetime

DB_FILE = "lms.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------------------- Utilities --------------------

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    # users: role is 'teacher' or 'student'
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        display_name TEXT,
        role TEXT,
        password_hash TEXT
    )
    ''')
    # classes
    c.execute('''
    CREATE TABLE IF NOT EXISTS classes (
        id TEXT PRIMARY KEY,
        class_name TEXT,
        access_code TEXT
    )
    ''')
    # materials
    c.execute('''
    CREATE TABLE IF NOT EXISTS materials (
        id TEXT PRIMARY KEY,
        class_id TEXT,
        title TEXT,
        access_code TEXT,
        file_path TEXT,
        external_url TEXT,
        type TEXT,
        uploaded_by TEXT,
        uploaded_at TEXT
    )
    ''')
    # attendance
    c.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id TEXT PRIMARY KEY,
        class_id TEXT,
        user_id TEXT,
        timestamp TEXT
    )
    ''')
    # notifications
    c.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        class_id TEXT,
        message TEXT,
        created_at TEXT
    )
    ''')
    # forum posts
    c.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        class_id TEXT,
        user_id TEXT,
        content TEXT,
        created_at TEXT
    )
    ''')
    # tests and questions
    c.execute('''
    CREATE TABLE IF NOT EXISTS tests (
        id TEXT PRIMARY KEY,
        class_id TEXT,
        title TEXT,
        is_pretest INTEGER,
        created_by TEXT,
        created_at TEXT
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        test_id TEXT,
        text TEXT,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        option_e TEXT,
        correct_option TEXT
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS attempts (
        id TEXT PRIMARY KEY,
        test_id TEXT,
        user_id TEXT,
        submitted_at TEXT,
        score REAL
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS answers (
        id TEXT PRIMARY KEY,
        attempt_id TEXT,
        question_id TEXT,
        chosen_option TEXT
    )
    ''')
    conn.commit()
    conn.close()


def hash_password(pw: str):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def save_file(uploaded_file):
    # Save to uploads with unique name
    fn = f"{uuid.uuid4().hex}_{uploaded_file.name}"
    path = os.path.join(UPLOAD_DIR, fn)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def file_to_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    return b64


# -------------------- App: Initialization --------------------
init_db()

if "user" not in st.session_state:
    st.session_state.user = None

conn = get_conn()

# -------------------- Authentication --------------------

st.title("LMS Prototype - Streamlit")

menu = st.sidebar.selectbox("Menu", ["Home", "Daftar / Login", "Buat Kelas (Guru)", "Bantuan"])

if menu == "Home":
    if not st.session_state.user:
        st.info("Silakan login atau daftar terlebih dahulu di menu 'Daftar / Login'.")
    else:
        user = st.session_state.user
        st.success(f"Halo, {user['display_name']} ({user['role']})")

        # Show classes joined (by access) - simple view to enter class
        st.header("Masuk Kelas")
        c = conn.cursor()
        classes = c.execute("SELECT * FROM classes").fetchall()
        for cl in classes:
            st.subheader(cl['class_name'])
            if st.button(f"Masuk {cl['class_name']}", key=f"enter_{cl['id']}"):
                code = st.text_input("Masukkan kode akses kelas:", key=f"code_input_{cl['id']}")
                # NOTE: we can't show input and immediately check within same click without rerun; so open a modal-like flow
                if code:
                    if code == cl['access_code']:
                        st.session_state.current_class = dict(cl)
                        st.experimental_rerun()
                    else:
                        st.error("Kode akses salah.")
        # If class selected in session
        if 'current_class' in st.session_state:
            cl = st.session_state.current_class
            st.markdown(f"### Kelas: {cl['class_name']}")
            tab = st.tabs(["Materi", "Absen", "Forum", "Pre/Post Test", "Notifikasi", "Virtual Lab"])

            # ---------- Materi ----------
            with tab[0]:
                st.subheader("Materi Kelas")
                c = conn.cursor()
                mats = c.execute("SELECT * FROM materials WHERE class_id = ?", (cl['id'],)).fetchall()
                for m in mats:
                    st.markdown(f"**{m['title']}** (tipe: {m['type']})")
                    # require material access code if set
                    if m['access_code']:
                        code = st.text_input(f"Masukkan kode akses materi untuk {m['title']}", key=f"matcode_{m['id']}")
                        if code != m['access_code']:
                            st.warning("Masukkan kode materi untuk melihat konten")
                            continue
                    # show based on type
                    if m['type'] in ('pdf', 'flipbook') and m['file_path']:
                        b64 = file_to_base64(m['file_path'])
                        st.components.v1.html(f"<iframe src='data:application/pdf;base64,{b64}' width='100%' height='600px'></iframe>", height=600)
                    elif m['type'] == 'liveworksheets' and m['external_url']:
                        st.components.v1.iframe(m['external_url'], height=700)
                    elif m['type'] == 'video':
                        # show inline video
                        if m['file_path']:
                            st.video(open(m['file_path'], 'rb'))
                        elif m['external_url']:
                            st.video(m['external_url'])
                    elif m['type'] == 'iframe' and m['external_url']:
                        st.components.v1.iframe(m['external_url'], height=700)
                    st.markdown("---")
                # upload material (teacher only)
                if st.session_state.user['role'] == 'teacher':
                    st.write("-- Upload Materi Baru --")
                    title = st.text_input("Judul Materi")
                    mtype = st.selectbox("Tipe", ['pdf', 'flipbook', 'liveworksheets', 'video', 'iframe'])
                    mat_code = st.text_input("Kode akses materi (opsional)")
                    uploaded = st.file_uploader("Upload file (pdf / video) jika ada", type=['pdf', 'mp4', 'mov', 'webm'])
                    external = st.text_input("External URL (misal iframe, liveworksheets, atau video URL)")
                    if st.button("Simpan Materi"):
                        mp = None
                        if uploaded:
                            mp = save_file(uploaded)
                        mid = uuid.uuid4().hex
                        conn.execute("INSERT INTO materials (id, class_id, title, access_code, file_path, external_url, type, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                     (mid, cl['id'], title, mat_code, mp, external, mtype, st.session_state.user['id'], datetime.now().isoformat()))
                        conn.commit()
                        st.experimental_rerun()

            # ---------- Absen ----------
            with tab[1]:
                st.subheader("Absen")
                if st.button("Isi Absen Sekarang"):
                    att_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO attendance (id, class_id, user_id, timestamp) VALUES (?,?,?,?)",
                                 (att_id, cl['id'], st.session_state.user['id'], datetime.now().isoformat()))
                    conn.commit()
                    st.success("Absen tercatat")
                # show recent attendance
                rows = conn.execute("SELECT a.timestamp, u.display_name FROM attendance a JOIN users u ON a.user_id=u.id WHERE a.class_id=? ORDER BY a.timestamp DESC LIMIT 20", (cl['id'],)).fetchall()
                st.write("Absen terakhir:")
                for r in rows:
                    st.write(f"{r['display_name']} — {r['timestamp']}")

            # ---------- Forum ----------
            with tab[2]:
                st.subheader("Forum Diskusi")
                posts = conn.execute("SELECT p.*, u.display_name FROM posts p JOIN users u ON p.user_id=u.id WHERE p.class_id=? ORDER BY p.created_at DESC", (cl['id'],)).fetchall()
                for p in posts:
                    st.markdown(f"**{p['display_name']}** — _{p['created_at']}_")
                    st.write(p['content'])
                    st.markdown("---")
                new_post = st.text_area("Tulis pertanyaan atau diskusi baru")
                if st.button("Post Diskusi") and new_post.strip():
                    pid = uuid.uuid4().hex
                    conn.execute("INSERT INTO posts (id, class_id, user_id, content, created_at) VALUES (?,?,?,?,?)",
                                 (pid, cl['id'], st.session_state.user['id'], new_post, datetime.now().isoformat()))
                    conn.commit()
                    # create notification for class
                    nid = uuid.uuid4().hex
                    conn.execute("INSERT INTO notifications (id, class_id, message, created_at) VALUES (?,?,?,?)",
                                 (nid, cl['id'], f"Diskusi baru oleh {st.session_state.user['display_name']}", datetime.now().isoformat()))
                    conn.commit()
                    st.experimental_rerun()

            # ---------- Pre/Post Test ----------
            with tab[3]:
                st.subheader("Pre/Post Test")
                tests = conn.execute("SELECT * FROM tests WHERE class_id=?", (cl['id'],)).fetchall()
                for t in tests:
                    st.markdown(f"**{t['title']}** — {'Pretest' if t['is_pretest'] else 'Postest'}")
                    if st.button("Mulai", key=f"start_{t['id']}"):
                        st.session_state.current_test = dict(t)
                        st.experimental_rerun()
                if st.session_state.user['role'] == 'teacher':
                    st.write("-- Buat Test Baru --")
                    ttl = st.text_input("Judul Test")
                    is_pre = st.checkbox("Pretest? (Kosong = Postest)")
                    if st.button("Buat Test") and ttl.strip():
                        tid = uuid.uuid4().hex
                        conn.execute("INSERT INTO tests (id, class_id, title, is_pretest, created_by, created_at) VALUES (?,?,?,?,?,?)",
                                     (tid, cl['id'], ttl, 1 if is_pre else 0, st.session_state.user['id'], datetime.now().isoformat()))
                        conn.commit()
                        st.experimental_rerun()

                # Start test flow
                if 'current_test' in st.session_state:
                    t = st.session_state.current_test
                    st.markdown(f"### Mengerjakan: {t['title']}")
                    qs = conn.execute("SELECT * FROM questions WHERE test_id=?", (t['id'],)).fetchall()
                    if not qs:
                        st.warning("Belum ada soal. Jika Anda guru, tambahkan soal di panel guru untuk test ini.")
                    else:
                        # show questions and collect answers
                        answers = {}
                        for q in qs:
                            st.write(q['text'])
                            opt = st.radio("Pilih jawaban:", ('A', 'B', 'C', 'D', 'E'), key=f"q_{q['id']}")
                            answers[q['id']] = opt
                        if st.button("Kirim Jawaban"):
                            attempt_id = uuid.uuid4().hex
                            score = 0
                            for qid, chosen in answers.items():
                                qrow = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
                                if qrow['correct_option'] == chosen:
                                    score += 1
                            score_val = (score / len(qs)) * 100
                            conn.execute("INSERT INTO attempts (id, test_id, user_id, submitted_at, score) VALUES (?,?,?,?,?)",
                                         (attempt_id, t['id'], st.session_state.user['id'], datetime.now().isoformat(), score_val))
                            for qid, chosen in answers.items():
                                aid = uuid.uuid4().hex
                                conn.execute("INSERT INTO answers (id, attempt_id, question_id, chosen_option) VALUES (?,?,?,?)",
                                             (aid, attempt_id, qid, chosen))
                            conn.commit()
                            st.success(f"Tersubmit. Nilai: {score_val:.1f}")
                            # notify teacher
                            nid = uuid.uuid4().hex
                            conn.execute("INSERT INTO notifications (id, class_id, message, created_at) VALUES (?,?,?,?)",
                                         (nid, cl['id'], f"{st.session_state.user['display_name']} selesai {t['title']}", datetime.now().isoformat()))
                            conn.commit()
                            del st.session_state['current_test']
                            st.experimental_rerun()

                    # teacher: add questions
                    if st.session_state.user['role'] == 'teacher':
                        st.write("-- Tambah Soal (MCQ) --")
                        qtext = st.text_area("Teks Soal")
                        a = st.text_input("Opsi A")
                        b = st.text_input("Opsi B")
                        copt = st.text_input("Opsi C")
                        d = st.text_input("Opsi D")
                        e = st.text_input("Opsi E")
                        correct = st.selectbox("Kunci jawaban", ['A','B','C','D','E'])
                        if st.button("Tambah Soal") and qtext.strip():
                            qid = uuid.uuid4().hex
                            conn.execute("INSERT INTO questions (id, test_id, text, option_a, option_b, option_c, option_d, option_e, correct_option) VALUES (?,?,?,?,?,?,?,?,?)",
                                         (qid, t['id'], qtext, a, b, copt, d, e, correct))
                            conn.commit()
                            st.experimental_rerun()

            # ---------- Notifications ----------
            with tab[4]:
                st.subheader("Notifikasi")
                rows = conn.execute("SELECT * FROM notifications WHERE class_id=? ORDER BY created_at DESC LIMIT 50", (cl['id'],)).fetchall()
                for r in rows:
                    st.write(f"[{r['created_at']}] {r['message']}")
                if st.session_state.user['role'] == 'teacher':
                    new_notif = st.text_input("Tulis notifikasi untuk peserta kelas")
                    if st.button("Kirim Notifikasi") and new_notif.strip():
                        nid = uuid.uuid4().hex
                        conn.execute("INSERT INTO notifications (id, class_id, message, created_at) VALUES (?,?,?,?)",
                                     (nid, cl['id'], new_notif, datetime.now().isoformat()))
                        conn.commit()
                        st.experimental_rerun()

            # ---------- Virtual Lab ----------
            with tab[5]:
                st.subheader("Virtual Laboratory (Embed PhET atau resource iframe)")
                st.write("Masukkan URL iframe dari PhET atau resource virtual lab lain")
                url = st.text_input("URL Iframe (misal: https://phet.colorado.edu/sims/html/pendulum/latest/pendulum_en.html)")
                if st.button("Tambahkan Embed") and url.strip():
                    mid = uuid.uuid4().hex
                    conn.execute("INSERT INTO materials (id, class_id, title, access_code, file_path, external_url, type, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (mid, cl['id'], "Virtual Lab", '', None, url, 'iframe', st.session_state.user['id'], datetime.now().isoformat()))
                    conn.commit()
                    st.experimental_rerun()
                # show existing iframes
                embeds = conn.execute("SELECT * FROM materials WHERE class_id=? AND type='iframe'", (cl['id'],)).fetchall()
                for e in embeds:
                    st.markdown(f"**{e['title']}**")
                    st.components.v1.iframe(e['external_url'], height=700)


# -------------------- Daftar / Login --------------------

elif menu == "Daftar / Login":
    st.header("Akun")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daftar")
        username = st.text_input("Username (unique)", key="reg_user")
        display = st.text_input("Nama tampil", key="reg_display")
        role = st.selectbox("Peran", ['student', 'teacher'], key='reg_role')
        pw = st.text_input("Password", type='password', key='reg_pw')
        if st.button("Daftar"):
            if not username or not pw:
                st.error("Username dan password diperlukan")
            else:
                uid = uuid.uuid4().hex
                try:
                    conn.execute("INSERT INTO users (id, username, display_name, role, password_hash) VALUES (?,?,?,?,?)",
                                 (uid, username, display, role, hash_password(pw)))
                    conn.commit()
                    st.success("Akun dibuat. Silakan login di kolom sebelah.")
                except sqlite3.IntegrityError:
                    st.error("Username sudah dipakai")
    with col2:
        st.subheader("Login")
        usern = st.text_input("Username", key='login_user')
        pww = st.text_input("Password", type='password', key='login_pw')
        if st.button("Login"):
            row = conn.execute("SELECT * FROM users WHERE username=?", (usern,)).fetchone()
            if row and row['password_hash'] == hash_password(pww):
                st.session_state.user = dict(row)
                st.success("Login berhasil")
                st.experimental_rerun()
            else:
                st.error("Login gagal")

# -------------------- Buat Kelas (Guru) --------------------
elif menu == "Buat Kelas (Guru)":
    st.header("Buat Kelas")
    if not st.session_state.user or st.session_state.user['role'] != 'teacher':
        st.warning("Hanya guru yang dapat membuat kelas. Silakan login sebagai guru.")
    else:
        cname = st.text_input("Nama Kelas")
        acode = st.text_input("Kode Akses Kelas (contoh: KLS2025) — simpan dan bagikan ke siswa")
        if st.button("Buat Kelas") and cname.strip() and acode.strip():
            cid = uuid.uuid4().hex
            conn.execute("INSERT INTO classes (id, class_name, access_code) VALUES (?,?,?)", (cid, cname, acode))
            conn.commit()
            st.success("Kelas dibuat. Bagikan kode akses ke siswa.")

# -------------------- Bantuan --------------------
elif menu == "Bantuan":
    st.header("Bantuan & Petunjuk Singkat")
    st.write("1. Jalankan aplikasi: `streamlit run streamlit_lms_app.py`")
    st.write("2. Daftar sebagai guru atau siswa di menu Akun.")
    st.write("3. Guru membuat kelas di menu 'Buat Kelas', lalu berikan kode akses ke siswa.")
    st.write("4. Guru dapat mengupload materi, menambahkan virtual lab (iframe), membuat pre/post test, dan mengirim notifikasi.")
    st.write("5. Siswa masuk kelas menggunakan kode akses, mengisi absen, membuka materi (jika ada kode materi), mengikuti test, berdiskusi di forum, dan melihat notifikasi.")
    st.write("Catatan: Untuk produksi, tambahkan autentikasi yang lebih aman, koneksi cloud DB, dan penyimpanan file (S3 / GCS).")

# -------------------- Footer --------------------
st.sidebar.markdown("---")
st.sidebar.write("Versi prototype — single-file Streamlit")

# Close connection at end
conn.close()
