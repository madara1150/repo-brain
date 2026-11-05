"""Thai / English UI text."""

_lang = "th"

T = {
    "subtitle": ("ให้ Claude รู้จักโค้ดและข้อมูลของทีมคุณ", "Let Claude know your team's code and knowledge"),
    "tab_sources": ("โค้ดจาก GitHub", "GitHub code"),
    "tab_knowledge": ("ข้อมูลทีม", "Team knowledge"),
    "tab_teach": ("สอน Claude", "Teach Claude"),
    "tab_claude": ("เชื่อมกับ Claude", "Connect Claude"),
    "tab_settings": ("ตั้งค่า", "Settings"),
    # update bar
    "update": ("อัปเดตข้อมูล", "Update"),
    "check": ("ตรวจหาของใหม่", "Check for changes"),
    "cancel": ("ยกเลิก", "Cancel"),
    "idle_never": ("ยังไม่มีข้อมูล — เพิ่ม repo แล้วกด “อัปเดตข้อมูล”", "No data yet — add a repository and press “Update”"),
    "idle_status": ("ข้อมูล ณ {when} · {files} ไฟล์ · {modules} โมดูล · {notes} บันทึกทีม",
                    "Snapshot of {when} · {files} files · {modules} modules · {notes} team notes"),
    "updating": ("กำลังอัปเดต… {msg}", "Updating… {msg}"),
    "update_done": ("อัปเดตเสร็จ: {summary}", "Update finished: {summary}"),
    "update_failed": ("อัปเดตไม่สำเร็จบางรายการ", "Some updates failed"),
    "checking": ("กำลังตรวจกับ GitHub…", "Checking GitHub…"),
    "has_updates": ("มี commit ใหม่ใน {n} repo — กด “อัปเดตข้อมูล” เมื่อพร้อม",
                    "{n} repositories have new commits — press “Update” when ready"),
    "no_updates": ("ข้อมูลล่าสุดแล้ว", "Everything is up to date"),
    "mode_full": ("โหลดใหม่ทั้งหมด", "full download"),
    "mode_incremental": ("เปลี่ยน {n} ไฟล์", "{n} files changed"),
    "mode_unchanged": ("ไม่มีอะไรเปลี่ยน", "no changes"),
    "mode_folder": ("{n} บันทึก", "{n} notes"),
    "mode_error": ("ผิดพลาด", "error"),
    # sources
    "sources_hint": ("repo ที่จะให้ Claude อ่าน ข้อมูลจะอัปเดตเมื่อกดปุ่มเท่านั้น ระหว่างนั้นใช้ข้อมูลเดิม",
                     "Repositories Claude can read. Data changes only when you press Update; until then the last snapshot is used."),
    "col_repo": ("Repository", "Repository"),
    "col_branch": ("Branch", "Branch"),
    "col_commit": ("Commit", "Commit"),
    "col_synced": ("อัปเดตล่าสุด", "Last update"),
    "col_files": ("ไฟล์", "Files"),
    "col_state": ("สถานะ", "Status"),
    "add_repo": ("เพิ่ม repo", "Add repository"),
    "remove_repo": ("ลบ", "Remove"),
    "find_deps": ("หา repo ที่โมดูลต้องใช้ (Odoo)", "Find dependency repos (Odoo)"),
    "state_new": ("ยังไม่เคยอัปเดต", "never updated"),
    "state_ok": ("ล่าสุด", "up to date"),
    "state_behind": ("มี commit ใหม่", "new commits"),
    "state_unknown": ("—", "—"),
    "default_branch": ("(ค่าเริ่มต้นของ repo)", "(repository default)"),
    "add_repo_title": ("เพิ่ม repository", "Add repository"),
    "add_repo_label": ("ชื่อ repo หรือ URL ของ GitHub", "GitHub repository or URL"),
    "branch_label": ("Branch (เว้นว่าง = ค่าเริ่มต้น)", "Branch (empty = default)"),
    "bad_repo": ("รูปแบบไม่ถูกต้อง ใช้ owner/name หรือ URL ของ github.com", "Use owner/name or a github.com URL"),
    "dup_repo": ("มี repo นี้อยู่แล้ว", "This repository is already listed"),
    "confirm_remove": ("ลบ {repo} และข้อมูลที่ index ไว้?", "Remove {repo} and its indexed data?"),
    "deps_title": ("Repo ที่โมดูลต้องใช้", "Dependency repositories"),
    "deps_running": ("กำลังหาจาก PyPI…", "Looking up on PyPI…"),
    "deps_none": ("ไม่มี dependency ที่ขาด หรือยังไม่ได้อัปเดตข้อมูล", "No missing dependencies (or nothing indexed yet)"),
    "deps_intro": ("โมดูลเหล่านี้ถูกอ้างถึงใน depends แต่ยังไม่มีในข้อมูล เลือก repo ที่จะเพิ่ม (branch {ver}):",
                   "These modules are listed in depends but not indexed. Pick repositories to add (branch {ver}):"),
    "deps_core": ("ไม่พบใน OCA (น่าจะเป็น Odoo core หรือโมดูลส่วนตัว): {mods}",
                  "Not found in OCA (probably Odoo core or private): {mods}"),
    "deps_add": ("เพิ่ม repo ที่เลือก", "Add selected"),
    "n_modules": ("{n} โมดูล", "{n} modules"),
    # knowledge
    "kn_hint": ("ข้อมูลภายในที่ทุกคนในทีมเพิ่มได้และเห็นร่วมกัน เช่น กฎธุรกิจ ขั้นตอนงาน ข้อตกลงของทีม",
                "Internal notes everyone can add and share: business rules, procedures, team conventions."),
    "kn_where": ("เก็บข้อมูลทีมไว้ที่", "Store team knowledge in"),
    "kn_none": ("ไม่ใช้", "Not used"),
    "kn_github": ("GitHub repo แบบ private (แนะนำ)", "Private GitHub repository (recommended)"),
    "kn_folder": ("โฟลเดอร์แชร์ (Google Drive / OneDrive / NAS)", "Shared folder (Google Drive / OneDrive / NAS)"),
    "kn_repo": ("Repo", "Repository"),
    "kn_subdir": ("โฟลเดอร์ย่อย", "Subfolder"),
    "kn_folder_label": ("โฟลเดอร์", "Folder"),
    "browse": ("เลือก…", "Browse…"),
    "kn_github_note": ("ทุกคนต้องได้รับเชิญเข้า repo นี้ และใส่ GitHub token ในหน้าตั้งค่า "
                       "อย่าใช้ repo public เพราะข้อมูลภายในจะเปิดเผย",
                       "Everyone must be invited to this repository and enter a GitHub token in Settings. "
                       "Never use a public repository for internal data."),
    "kn_folder_note": ("ทุกคนเลือกโฟลเดอร์ที่ sync ร่วมกัน ข้อมูลไม่มีประวัติการแก้ไข", "Everyone picks the same synced folder. No edit history."),
    "kn_add": ("เพิ่มข้อมูล", "Add note"),
    "kn_list_empty": ("ยังไม่มีบันทึก กด “อัปเดตข้อมูล” เพื่อดึงของทีม หรือ “เพิ่มข้อมูล”",
                      "No notes yet. Press “Update” to fetch the team's notes, or “Add note”."),
    "kn_count": ("{n} บันทึก", "{n} notes"),
    "kn_dialog": ("เพิ่มข้อมูลให้ทีม", "Add a note for the team"),
    "kn_title": ("หัวข้อ", "Title"),
    "kn_tags": ("แท็ก (คั่นด้วย ,)", "Tags (comma separated)"),
    "kn_content": ("เนื้อหา (Markdown)", "Content (Markdown)"),
    "kn_save": ("บันทึกและแชร์", "Save and share"),
    "kn_saved": ("บันทึกแล้ว: {where}\nคนอื่นจะเห็นหลังจากกด “อัปเดตข้อมูล”", "Saved: {where}\nOthers see it after they press “Update”."),
    "kn_tip": ("เคล็ดลับ: ใน Claude พิมพ์ว่า “จำไว้ให้ทีมว่า …” ก็บันทึกได้เหมือนกัน",
               "Tip: in Claude, say “remember for the team that …” to save a note too."),
    # claude
    "cl_title": ("เชื่อม Repo Brain กับ Claude Desktop", "Connect Repo Brain to Claude Desktop"),
    "cl_body": ("Repo Brain ทำงานเป็น MCP server ให้ Claude ของแต่ละคน ใช้บัญชีและโควตา Claude ของคุณเอง ไม่ต้องมี API key",
                "Repo Brain runs as an MCP server for each person's Claude, using your own Claude account and quota — no API key."),
    "cl_connected": ("เชื่อมแล้ว", "Connected"),
    "cl_missing": ("ยังไม่ได้เชื่อม", "Not connected"),
    "cl_outdated": ("เชื่อมไว้กับแอปตัวอื่น — กดเชื่อมใหม่", "Points at another copy of the app — connect again"),
    "cl_no_desktop": ("ไม่พบ Claude Desktop ในเครื่องนี้ ติดตั้งจาก claude.ai/download ก่อน",
                      "Claude Desktop not found. Install it from claude.ai/download first."),
    "cl_connect": ("เชื่อมกับ Claude Desktop", "Connect to Claude Desktop"),
    "cl_disconnect": ("ยกเลิกการเชื่อม", "Disconnect"),
    "cl_steps": ("<b>ขั้นตอน</b><ol><li>กด “เชื่อมกับ Claude Desktop”</li><li>ปิด Claude Desktop ให้สนิทแล้วเปิดใหม่ (Quit ไม่ใช่แค่ปิดหน้าต่าง)</li>"
                 "<li>ในแชท ดูที่ปุ่ม <b>+</b> → Connectors จะเห็น <b>repo-brain</b></li><li>ถามได้เลย เช่น “model purchase.request ถูก inherit ที่โมดูลไหนบ้าง”</li></ol>",
                 "<b>Steps</b><ol><li>Press “Connect to Claude Desktop”</li><li>Quit Claude Desktop completely and open it again</li>"
                 "<li>In a chat, open <b>+</b> → Connectors and you'll see <b>repo-brain</b></li><li>Ask away, e.g. “which modules inherit purchase.request?”</li></ol>"),
    "cl_done": ("เชื่อมแล้ว ปิด Claude Desktop (Quit) แล้วเปิดใหม่หนึ่งครั้ง\nไฟล์ตั้งค่า: {path}",
                "Connected. Quit and reopen Claude Desktop once.\nConfig file: {path}"),
    "cl_broken": ("อ่านไฟล์ตั้งค่าของ Claude ไม่ได้ (JSON เสีย) จึงไม่ได้แก้ไข: {path}",
                  "Claude's config file is not valid JSON, so it was left untouched: {path}"),
    "cl_code": ("ใช้กับ Claude Code (ทางเลือก)", "Use with Claude Code (optional)"),
    "copy": ("คัดลอก", "Copy"),
    "copied": ("คัดลอกแล้ว", "Copied"),
    "cl_examples": ("<b>ตัวอย่างคำถาม</b><ul><li>โมดูล purchase_request_tier_validation ทำอะไร พึ่งโมดูลไหนบ้าง</li>"
                    "<li>field “ผู้ขอซื้อ” อยู่ใน model ไหน มีค่าเริ่มต้นยังไง</li><li>ใบขอซื้อของเราต้องอนุมัติกี่ขั้น (ดูข้อมูลทีมด้วย)</li>"
                    "<li>จำไว้ให้ทีมว่า: ปิดงวดบัญชีสิ้นปีต้องทำก่อนวันที่ 30 ก.ย.</li></ul>",
                    "<b>Example questions</b><ul><li>What does purchase_request_tier_validation do and what does it depend on?</li>"
                    "<li>Which model has the “Requested by” field and what is its default?</li><li>How many approval steps does our purchase request need? (check team notes too)</li>"
                    "<li>Remember for the team: year-end closing must be done before 30 Sep.</li></ul>"),
    # settings
    "st_token": ("GitHub token", "GitHub token"),
    "st_token_hint": ("ไม่บังคับสำหรับ repo public (ช่วยไม่ให้ติด rate limit) แต่จำเป็นสำหรับ repo ข้อมูลทีมแบบ private<br>"
                      "• repo ของบัญชีคนอื่น: <a href='https://github.com/settings/tokens/new?scopes=repo&description=Repo%20Brain'>สร้าง classic token</a> สิทธิ์ <b>repo</b><br>"
                      "• repo ของคุณเองหรือของ organization: <a href='https://github.com/settings/personal-access-tokens/new'>fine-grained token</a> "
                      "สิทธิ์ Contents: Read and write เฉพาะ repo นั้น<br>• ได้ไฟล์ตั้งค่าทีมมา: กด “นำเข้าการตั้งค่าทีม” ด้านบน ไม่ต้องสร้างเอง",
                      "Optional for public repositories (avoids rate limits), required for a private knowledge repository.<br>"
                      "• Repository owned by another person: <a href='https://github.com/settings/tokens/new?scopes=repo&description=Repo%20Brain'>create a classic token</a> with the <b>repo</b> scope<br>"
                      "• Your own or an organization's repository: a <a href='https://github.com/settings/personal-access-tokens/new'>fine-grained token</a> "
                      "with Contents: Read and write on that repository only<br>• Got a team settings file? Use “Import team settings” above instead"),
    "st_show": ("แสดง", "Show"),
    "st_test": ("ทดสอบ", "Test"),
    "st_token_ok": ("ใช้ได้ — เข้าสู่ระบบเป็น {login}", "Works — signed in as {login}"),
    "st_author": ("ชื่อผู้บันทึก", "Your name"),
    "st_author_hint": ("แสดงในบันทึกที่คุณเพิ่ม (เว้นว่าง = ชื่อ GitHub)", "Shown on notes you add (empty = GitHub login)"),
    "st_odoo": ("เวอร์ชัน Odoo", "Odoo version"),
    "st_odoo_hint": ("ใช้เลือก branch ตอนเพิ่ม repo ของ OCA", "Used as the branch when adding OCA repositories"),
    "st_lang": ("ภาษา", "Language"),
    "st_data": ("ที่เก็บข้อมูล", "Data folder"),
    "st_open": ("เปิดโฟลเดอร์", "Open folder"),
    "st_privacy": ("ข้อมูลทั้งหมดเก็บในเครื่องนี้ แอปติดต่อแค่ GitHub (ตอนกดอัปเดต/ตรวจ/เพิ่มข้อมูล) และ PyPI (ตอนหา dependency) "
                   "ส่วนที่ Claude อ่านจะส่งผ่าน Claude Desktop ของคุณเอง",
                   "Everything is stored on this computer. The app only contacts GitHub (update / check / add note) and PyPI "
                   "(dependency lookup). What Claude reads goes through your own Claude Desktop."),
    # teach tab
    "te_line_title": ("เคสถาม-ตอบจาก LINE", "Q&A cases from LINE"),
    "te_line_hint": ("เปิดไฟล์ที่ export จาก LINE (แชท → ตั้งค่า → ส่งออกประวัติการแชท) หรือวางข้อความ "
                     "แอปจะแยกเป็นเคสและปิดชื่อ เบอร์โทร อีเมล เลขบัตร ให้ก่อน",
                     "Open a chat exported from LINE (chat → settings → Export chat history) or paste text. "
                     "The app splits it into cases and hides names, phone numbers, emails and ID numbers first."),
    "te_open": ("เปิดไฟล์ LINE (.txt)…", "Open LINE export (.txt)…"),
    "te_paste": ("วางข้อความแชท…", "Paste chat text…"),
    "te_paste_hint": ("วางข้อความจาก LINE (ข้อความในคลิปบอร์ดถูกใส่ไว้ให้แล้ว)", "Paste text from LINE (the clipboard is already filled in)"),
    "te_screens": ("มีแค่ภาพหน้าจอ? ใน Claude Desktop กด <b>+</b> → <b>repo-brain</b> → <b>วิเคราะห์เคสจาก LINE</b> แล้วแนบรูป",
                   "Only screenshots? In Claude Desktop press <b>+</b> → <b>repo-brain</b> → <b>วิเคราะห์เคสจาก LINE</b> and attach them"),
    "te_flow_title": ("สอน flow การทำงาน", "Teach a work flow"),
    "te_flow_hint": ("Claude จะดูโค้ดก่อน แล้วถามคุณทีละขั้นจนอธิบาย flow กลับได้ถูก จากนั้นให้คุณอ่านร่างก่อนบันทึก",
                     "Claude reads the code first, then asks you step by step until it can explain the flow back "
                     "correctly, and shows you the draft before saving."),
    "te_flow_ph": ("เช่น ขอซื้อ-จัดซื้อ, เบิกจ่าย, โอนงบ", "e.g. purchase request to PO, disbursement"),
    "te_flow_copy": ("คัดลอกคำสั่งไปวางใน Claude", "Copy prompt for Claude"),
    "te_empty": ("เปิดไฟล์หรือวางแชท แล้วเลือกเคสทางซ้าย แก้หรือตัดข้อความที่ไม่เกี่ยวได้ก่อนส่ง",
                 "Open or paste a chat, pick a case on the left, and trim anything unrelated before sending."),
    "te_msgs": ("{n} ข้อความ", "{n} messages"),
    "te_loaded": ("พบ {n} เคส", "{n} cases found"),
    "te_copy_case": ("คัดลอกให้ Claude วิเคราะห์", "Copy for Claude to analyze"),
    "te_done": ("ทำเสร็จแล้ว ✓", "Mark done ✓"),
    "te_copied": ("คัดลอกแล้ว — เปิดแชทใหม่ใน Claude Desktop แล้ววาง (⌘V / Ctrl+V)",
                  "Copied — start a new chat in Claude Desktop and paste (⌘V / Ctrl+V)"),
    # team settings file
    "team_title": ("การตั้งค่าทีม", "Team settings"),
    "team_hint": ("คนเดียวตั้งค่าแล้วส่งออกเป็นไฟล์ คนอื่นกดนำเข้าก็ได้รายการ repo, ที่เก็บข้อมูลทีม, เวอร์ชัน Odoo และ token ครบ "
                  "(ชื่อผู้บันทึกและภาษาของแต่ละคนไม่ถูกเปลี่ยน) ไฟล์ที่มี token ให้ส่งทางช่องทางส่วนตัวเท่านั้น",
                  "One person sets things up and exports a file; everyone else imports it to get the repositories, team "
                  "knowledge location, Odoo version and token (each person's name and language stay). Share a file that "
                  "contains a token privately only."),
    "team_import": ("นำเข้าการตั้งค่าทีม…", "Import team settings…"),
    "team_export": ("ส่งออกการตั้งค่าทีม…", "Export team settings…"),
    "team_ask_token": ("ใส่ GitHub token ไว้ในไฟล์ด้วยไหม?\n\nใส่: คนในทีมไม่ต้องสร้าง token เอง (ควรใช้ fine-grained token "
                       "ที่จำกัดเฉพาะ repo ข้อมูลทีม)\nไม่ใส่: แต่ละคนต้องใส่ token ของตัวเอง",
                       "Include the GitHub token in the file?\n\nYes: teammates don't need their own token (use a fine-grained "
                       "token limited to the knowledge repository)\nNo: everyone enters their own token"),
    "team_exported": ("บันทึกแล้ว: {path}", "Saved: {path}"),
    "team_exported_token": ("บันทึกแล้ว: {path}\n\nไฟล์นี้มี token อยู่ ส่งให้ทีมทางแชทส่วนตัวเท่านั้น "
                            "อย่าใส่ไว้ใน repo, อีเมลกลุ่มใหญ่ หรือที่สาธารณะ",
                            "Saved: {path}\n\nThis file contains the token. Send it to the team privately only — "
                            "never commit it or post it anywhere public."),
    "team_bad": ("เปิดไฟล์ไม่ได้: {err}", "Cannot open the file: {err}"),
    "team_summary": ("จะใช้การตั้งค่าจากไฟล์นี้แทนของเดิม:\n\nRepo:\n{repos}\n\nข้อมูลทีม: {knowledge}\nOdoo: {odoo}\nToken: {token}\n\nดำเนินการต่อ?",
                     "Replace your settings with this file:\n\nRepositories:\n{repos}\n\nTeam knowledge: {knowledge}\nOdoo: {odoo}\nToken: {token}\n\nContinue?"),
    "team_has_token": ("มีในไฟล์", "included"),
    "team_no_token": ("ไม่มีในไฟล์ (ใช้ของคุณเอง)", "not included (yours is kept)"),
    "team_imported": ("นำเข้าแล้ว กด “อัปเดตข้อมูล” เพื่อโหลดโค้ดและข้อมูลทีม แล้วไปที่แท็บ “เชื่อมกับ Claude”",
                      "Imported. Press “Update” to load the code and team notes, then open “Connect Claude”."),
    "team_need_name": ("กรอก “ชื่อผู้บันทึก” ในหน้าตั้งค่าด้วย เพื่อให้รู้ว่าใครเป็นคนเพิ่มบันทึก",
                       "Fill in “Your name” in Settings so notes show who added them."),
    "team_need_folder": ("ข้อมูลทีมเป็นแบบโฟลเดอร์แชร์ ไปที่แท็บ “ข้อมูลทีม” แล้วเลือกโฟลเดอร์ในเครื่องของคุณ",
                         "Team knowledge uses a shared folder: pick it on your computer in the “Team knowledge” tab."),
    "error": ("เกิดข้อผิดพลาด", "Something went wrong"),
}


def set_language(lang: str):
    global _lang
    _lang = "en" if lang == "en" else "th"


def language() -> str:
    return _lang


def tr(key: str, **kw) -> str:
    th, en = T[key]
    text = en if _lang == "en" else th
    return text.format(**kw) if kw else text
