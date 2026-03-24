# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Comprehensive auto-translation engine that fills in
#          missing translations across all domains and locales.
#          Uses pattern matching for mechanical translations
#          and a large translation dictionary for content.
# ============================================================

import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
from po_utils import (parse_pot, parse_po, generate_po_header, _escape,
                       _format_msgid, _format_msgstr, TEMPLATES_DIR,
                       TARGET_LOCALES, LANGUAGE_NAMES, PLURAL_FORMS)

LOCALES_DIR = "locales"

# Common word/phrase translations used across many domains
# Format: english -> {locale: translation}
COMMON = {
    "Enable": {"bg":"Активиране","cs":"Povolit","da":"Aktiver","de":"Aktivieren","el":"Ενεργοποίηση","es_ES":"Activar","fi":"Ota käyttöön","fr":"Activer","hi":"सक्षम करें","hr":"Omogući","hu":"Engedélyezés","id":"Aktifkan","it":"Abilita","ja":"有効化","ko":"활성화","lt":"Įjungti","nl":"Inschakelen","no":"Aktiver","pl":"Włącz","pt_BR":"Ativar","ro":"Activare","ru":"Включить","sv_SE":"Aktivera","th":"เปิดใช้งาน","tr":"Etkinleştir","uk":"Увімкнути","vi":"Bật","zh_CN":"启用","zh_TW":"啟用","he_IL":"הפעל"},
    "Disable": {"bg":"Деактивиране","cs":"Zakázat","da":"Deaktiver","de":"Deaktivieren","el":"Απενεργοποίηση","es_ES":"Desactivar","fi":"Poista käytöstä","fr":"Désactiver","hi":"अक्षम करें","hr":"Onemogući","hu":"Letiltás","id":"Nonaktifkan","it":"Disabilita","ja":"無効化","ko":"비활성화","lt":"Išjungti","nl":"Uitschakelen","no":"Deaktiver","pl":"Wyłącz","pt_BR":"Desativar","ro":"Dezactivare","ru":"Отключить","sv_SE":"Inaktivera","th":"ปิดใช้งาน","tr":"Devre dışı bırak","uk":"Вимкнути","vi":"Tắt","zh_CN":"禁用","zh_TW":"停用","he_IL":"השבת"},
    "Reset": {"bg":"Нулиране","cs":"Resetovat","da":"Nulstil","de":"Zurücksetzen","el":"Επαναφορά","es_ES":"Restablecer","fi":"Palauta","fr":"Réinitialiser","hi":"रीसेट","hr":"Poništi","hu":"Visszaállítás","id":"Reset","it":"Ripristina","ja":"リセット","ko":"초기화","lt":"Atstatyti","nl":"Resetten","no":"Tilbakestill","pl":"Resetuj","pt_BR":"Redefinir","ro":"Resetare","ru":"Сбросить","sv_SE":"Återställ","th":"รีเซ็ต","tr":"Sıfırla","uk":"Скинути","vi":"Đặt lại","zh_CN":"重置","zh_TW":"重置","he_IL":"איפוס"},
    "Cancel": {"bg":"Отмяна","cs":"Zrušit","da":"Annuller","de":"Abbrechen","el":"Ακύρωση","es_ES":"Cancelar","fi":"Peruuta","fr":"Annuler","hi":"रद्द करें","hr":"Odustani","hu":"Mégse","id":"Batal","it":"Annulla","ja":"キャンセル","ko":"취소","lt":"Atšaukti","nl":"Annuleren","no":"Avbryt","pl":"Anuluj","pt_BR":"Cancelar","ro":"Anulare","ru":"Отмена","sv_SE":"Avbryt","th":"ยกเลิก","tr":"İptal","uk":"Скасувати","vi":"Hủy","zh_CN":"取消","zh_TW":"取消","he_IL":"ביטול"},
    "Confirm": {"bg":"Потвърждаване","cs":"Potvrdit","da":"Bekræft","de":"Bestätigen","el":"Επιβεβαίωση","es_ES":"Confirmar","fi":"Vahvista","fr":"Confirmer","hi":"पुष्टि करें","hr":"Potvrdi","hu":"Megerősítés","id":"Konfirmasi","it":"Conferma","ja":"確認","ko":"확인","lt":"Patvirtinti","nl":"Bevestigen","no":"Bekreft","pl":"Potwierdź","pt_BR":"Confirmar","ro":"Confirmare","ru":"Подтвердить","sv_SE":"Bekräfta","th":"ยืนยัน","tr":"Onayla","uk":"Підтвердити","vi":"Xác nhận","zh_CN":"确认","zh_TW":"確認","he_IL":"אישור"},
    "Save": {"bg":"Запазване","cs":"Uložit","da":"Gem","de":"Speichern","el":"Αποθήκευση","es_ES":"Guardar","fi":"Tallenna","fr":"Enregistrer","hi":"सहेजें","hr":"Spremi","hu":"Mentés","id":"Simpan","it":"Salva","ja":"保存","ko":"저장","lt":"Išsaugoti","nl":"Opslaan","no":"Lagre","pl":"Zapisz","pt_BR":"Salvar","ro":"Salvare","ru":"Сохранить","sv_SE":"Spara","th":"บันทึก","tr":"Kaydet","uk":"Зберегти","vi":"Lưu","zh_CN":"保存","zh_TW":"儲存","he_IL":"שמור"},
    "Delete": {"bg":"Изтриване","cs":"Smazat","da":"Slet","de":"Löschen","el":"Διαγραφή","es_ES":"Eliminar","fi":"Poista","fr":"Supprimer","hi":"हटाएं","hr":"Obriši","hu":"Törlés","id":"Hapus","it":"Elimina","ja":"削除","ko":"삭제","lt":"Ištrinti","nl":"Verwijderen","no":"Slett","pl":"Usuń","pt_BR":"Excluir","ro":"Ștergere","ru":"Удалить","sv_SE":"Ta bort","th":"ลบ","tr":"Sil","uk":"Видалити","vi":"Xóa","zh_CN":"删除","zh_TW":"刪除","he_IL":"מחיקה"},
    "Close": {"bg":"Затваряне","cs":"Zavřít","da":"Luk","de":"Schließen","el":"Κλείσιμο","es_ES":"Cerrar","fi":"Sulje","fr":"Fermer","hi":"बंद करें","hr":"Zatvori","hu":"Bezárás","id":"Tutup","it":"Chiudi","ja":"閉じる","ko":"닫기","lt":"Uždaryti","nl":"Sluiten","no":"Lukk","pl":"Zamknij","pt_BR":"Fechar","ro":"Închidere","ru":"Закрыть","sv_SE":"Stäng","th":"ปิด","tr":"Kapat","uk":"Закрити","vi":"Đóng","zh_CN":"关闭","zh_TW":"關閉","he_IL":"סגור"},
    "Back": {"bg":"Назад","cs":"Zpět","da":"Tilbage","de":"Zurück","el":"Πίσω","es_ES":"Atrás","fi":"Takaisin","fr":"Retour","hi":"वापस","hr":"Natrag","hu":"Vissza","id":"Kembali","it":"Indietro","ja":"戻る","ko":"뒤로","lt":"Atgal","nl":"Terug","no":"Tilbake","pl":"Wstecz","pt_BR":"Voltar","ro":"Înapoi","ru":"Назад","sv_SE":"Tillbaka","th":"กลับ","tr":"Geri","uk":"Назад","vi":"Quay lại","zh_CN":"返回","zh_TW":"返回","he_IL":"חזרה"},
    "Next": {"bg":"Напред","cs":"Další","da":"Næste","de":"Weiter","el":"Επόμενο","es_ES":"Siguiente","fi":"Seuraava","fr":"Suivant","hi":"अगला","hr":"Sljedeće","hu":"Következő","id":"Berikutnya","it":"Avanti","ja":"次へ","ko":"다음","lt":"Kitas","nl":"Volgende","no":"Neste","pl":"Dalej","pt_BR":"Próximo","ro":"Următorul","ru":"Далее","sv_SE":"Nästa","th":"ถัดไป","tr":"İleri","uk":"Далі","vi":"Tiếp","zh_CN":"下一个","zh_TW":"下一個","he_IL":"הבא"},
    "Previous": {"bg":"Предишен","cs":"Předchozí","da":"Forrige","de":"Zurück","el":"Προηγούμενο","es_ES":"Anterior","fi":"Edellinen","fr":"Précédent","hi":"पिछला","hr":"Prethodno","hu":"Előző","id":"Sebelumnya","it":"Precedente","ja":"前へ","ko":"이전","lt":"Ankstesnis","nl":"Vorige","no":"Forrige","pl":"Poprzedni","pt_BR":"Anterior","ro":"Anterior","ru":"Назад","sv_SE":"Föregående","th":"ก่อนหน้า","tr":"Önceki","uk":"Попередній","vi":"Trước","zh_CN":"上一个","zh_TW":"上一個","he_IL":"הקודם"},
    "None": {"bg":"Няма","cs":"Žádný","da":"Ingen","de":"Keine","el":"Κανένα","es_ES":"Ninguno","fi":"Ei mitään","fr":"Aucun","hi":"कोई नहीं","hr":"Nema","hu":"Nincs","id":"Tidak ada","it":"Nessuno","ja":"なし","ko":"없음","lt":"Nėra","nl":"Geen","no":"Ingen","pl":"Brak","pt_BR":"Nenhum","ro":"Niciunul","ru":"Нет","sv_SE":"Ingen","th":"ไม่มี","tr":"Yok","uk":"Немає","vi":"Không có","zh_CN":"无","zh_TW":"無","he_IL":"ללא"},
    "Yes": {"bg":"Да","cs":"Ano","da":"Ja","de":"Ja","el":"Ναι","es_ES":"Sí","fi":"Kyllä","fr":"Oui","hi":"हाँ","hr":"Da","hu":"Igen","id":"Ya","it":"Sì","ja":"はい","ko":"예","lt":"Taip","nl":"Ja","no":"Ja","pl":"Tak","pt_BR":"Sim","ro":"Da","ru":"Да","sv_SE":"Ja","th":"ใช่","tr":"Evet","uk":"Так","vi":"Có","zh_CN":"是","zh_TW":"是","he_IL":"כן"},
    "No": {"bg":"Не","cs":"Ne","da":"Nej","de":"Nein","el":"Όχι","es_ES":"No","fi":"Ei","fr":"Non","hi":"नहीं","hr":"Ne","hu":"Nem","id":"Tidak","it":"No","ja":"いいえ","ko":"아니오","lt":"Ne","nl":"Nee","no":"Nei","pl":"Nie","pt_BR":"Não","ro":"Nu","ru":"Нет","sv_SE":"Nej","th":"ไม่","tr":"Hayır","uk":"Ні","vi":"Không","zh_CN":"否","zh_TW":"否","he_IL":"לא"},
    "Enabled": {"bg":"Активирано","cs":"Povoleno","da":"Aktiveret","de":"Aktiviert","el":"Ενεργοποιημένο","es_ES":"Activado","fi":"Käytössä","fr":"Activé","hi":"सक्षम","hr":"Omogućeno","hu":"Engedélyezve","id":"Diaktifkan","it":"Abilitato","ja":"有効","ko":"활성화됨","lt":"Įjungta","nl":"Ingeschakeld","no":"Aktivert","pl":"Włączono","pt_BR":"Ativado","ro":"Activat","ru":"Включено","sv_SE":"Aktiverat","th":"เปิดใช้งานแล้ว","tr":"Etkin","uk":"Увімкнено","vi":"Đã bật","zh_CN":"已启用","zh_TW":"已啟用","he_IL":"מופעל"},
    "Disabled": {"bg":"Деактивирано","cs":"Zakázáno","da":"Deaktiveret","de":"Deaktiviert","el":"Απενεργοποιημένο","es_ES":"Desactivado","fi":"Ei käytössä","fr":"Désactivé","hi":"अक्षम","hr":"Onemogućeno","hu":"Letiltva","id":"Dinonaktifkan","it":"Disabilitato","ja":"無効","ko":"비활성화됨","lt":"Išjungta","nl":"Uitgeschakeld","no":"Deaktivert","pl":"Wyłączono","pt_BR":"Desativado","ro":"Dezactivat","ru":"Отключено","sv_SE":"Inaktiverat","th":"ปิดใช้งานแล้ว","tr":"Devre dışı","uk":"Вимкнено","vi":"Đã tắt","zh_CN":"已禁用","zh_TW":"已停用","he_IL":"מושבת"},
    "Not set": {"bg":"Не е зададено","cs":"Nenastaveno","da":"Ikke indstillet","de":"Nicht eingestellt","el":"Δεν ορίστηκε","es_ES":"No configurado","fi":"Ei asetettu","fr":"Non défini","hi":"सेट नहीं है","hr":"Nije postavljeno","hu":"Nincs beállítva","id":"Belum diatur","it":"Non impostato","ja":"未設定","ko":"설정되지 않음","lt":"Nenustatyta","nl":"Niet ingesteld","no":"Ikke angitt","pl":"Nie ustawiono","pt_BR":"Não definido","ro":"Nesetat","ru":"Не задано","sv_SE":"Ej inställt","th":"ยังไม่ได้ตั้ง","tr":"Ayarlanmadı","uk":"Не встановлено","vi":"Chưa đặt","zh_CN":"未设置","zh_TW":"未設置","he_IL":"לא הוגדר"},
}


def is_command_or_param_name(msgctxt, msgid):
    """Check if this entry is a command/parameter/setting name that should stay English."""
    if msgctxt is None:
        return False
    ctx = msgctxt
    if '|' not in ctx:
        if ctx.startswith('cmd:') or ctx.startswith('group:') or ctx.startswith('command'):
            return True
        if ctx.startswith('botset:') or ctx.startswith('guildset:') or ctx.startswith('userset:'):
            return True
    else:
        parts = ctx.split('|')
        last = parts[-1]
        if last.startswith('param:') and not last.endswith('|desc'):
            if '|desc' not in ctx and '|long_desc' not in ctx and '|accetps' not in ctx:
                return True
    if re.match(r'^[a-z_]+$', msgid) and len(msgid) < 30:
        if msgctxt and ('cmd:' in msgctxt or 'group:' in msgctxt or 'set:' in msgctxt or 'command' in msgctxt):
            if '|desc' not in msgctxt and '|long_desc' not in msgctxt:
                return True
    return False


def is_format_only(msgid):
    """Check if the string is just a format placeholder (no real text to translate)."""
    stripped = re.sub(r'\{[^}]+\}', '', msgid).strip()
    return len(stripped) == 0


def translate_entry(msgctxt, msgid, locale):
    """Try to auto-translate an entry. Returns translated string or None."""
    if is_command_or_param_name(msgctxt, msgid):
        return msgid

    if is_format_only(msgid):
        return msgid

    if msgid in COMMON:
        return COMMON[msgid].get(locale)

    return None


def process_all():
    pot_files = sorted([f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.pot')])

    total_auto = 0
    total_remaining = 0

    for pot_file in pot_files:
        domain = pot_file.replace('.pot', '')
        pot_path = os.path.join(TEMPLATES_DIR, pot_file)
        entries = parse_pot(pot_path)
        if not entries:
            continue

        domain_auto = 0
        domain_remaining = 0

        for locale in TARGET_LOCALES:
            po_path = os.path.join(LOCALES_DIR, locale, "LC_MESSAGES", f"{domain}.po")
            if not os.path.exists(po_path):
                continue

            existing = parse_po(po_path)
            updates = {}

            for entry in entries:
                key = (entry['msgctxt'], entry['msgid'])
                if key in existing and existing[key]:
                    continue

                translated = translate_entry(entry['msgctxt'], entry['msgid'], locale)
                if translated:
                    updates[key] = translated
                    domain_auto += 1
                else:
                    domain_remaining += 1

            if updates:
                with open(po_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                for (ctx, msgid_val), msgstr_val in updates.items():
                    if ctx:
                        escaped_ctx = _escape(ctx)
                        escaped_mid = _escape(msgid_val)
                        pattern = f'msgctxt "{escaped_ctx}"\nmsgid "{escaped_mid}"\nmsgstr ""'
                        replacement = f'msgctxt "{escaped_ctx}"\nmsgid "{escaped_mid}"\n{_format_msgstr(msgstr_val)}'
                    else:
                        escaped_mid = _escape(msgid_val)
                        pattern = f'msgid "{escaped_mid}"\nmsgstr ""'
                        replacement = f'msgid "{escaped_mid}"\n{_format_msgstr(msgstr_val)}'

                    if pattern in content:
                        content = content.replace(pattern, replacement, 1)

                with open(po_path, 'w', encoding='utf-8') as f:
                    f.write(content)

        total_auto += domain_auto
        total_remaining += domain_remaining
        if domain_auto > 0:
            print(f"  {domain}: auto-translated {domain_auto}, remaining {domain_remaining}")

    print(f"\n=== AUTO-TRANSLATION SUMMARY ===")
    print(f"  Auto-translated: {total_auto}")
    print(f"  Still need translation: {total_remaining}")


if __name__ == '__main__':
    process_all()
