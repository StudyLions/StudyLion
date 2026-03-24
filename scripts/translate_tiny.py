# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-13
# Purpose: Generate translations for tiny domains:
#          base, topgg, timer-gui, core_config, profile-gui
# ============================================================

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
from po_utils import parse_pot, write_po_files, load_existing_translations, TEMPLATES_DIR, TARGET_LOCALES

def load_salvaged(domain):
    """Load salvaged Transifex translations for a domain."""
    json_path = os.path.join(os.path.dirname(__file__), 'salvaged_translations.json')
    if not os.path.exists(json_path):
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        all_salvaged = json.load(f)
    if domain not in all_salvaged:
        return {}
    result = {}
    for key_str, locale_map in all_salvaged[domain].items():
        parts = key_str.split('|||', 1)
        ctx = parts[0] if parts[0] else None
        msgid = parts[1]
        result[(ctx, msgid)] = locale_map
    return result

# =========================================================
# TRANSLATIONS
# Format: {(msgctxt, msgid): {locale: translation}}
# Command names stay as English (lowercase ASCII only)
# =========================================================

BASE_TRANSLATIONS = {
    (None, "You cannot use this interface!"): {
        "bg": "Не можете да използвате този интерфейс!",
        "cs": "Toto rozhraní nemůžete používat!",
        "da": "Du kan ikke bruge denne grænseflade!",
        "de": "Du kannst diese Oberfläche nicht verwenden!",
        "el": "Δεν μπορείτε να χρησιμοποιήσετε αυτή τη διεπαφή!",
        "es_ES": "¡No puedes usar esta interfaz!",
        "fi": "Et voi käyttää tätä käyttöliittymää!",
        "fr": "Vous ne pouvez pas utiliser cette interface !",
        "hi": "आप इस इंटरफ़ेस का उपयोग नहीं कर सकते!",
        "hr": "Ne možete koristiti ovo sučelje!",
        "hu": "Nem használhatod ezt a felületet!",
        "id": "Anda tidak dapat menggunakan antarmuka ini!",
        "it": "Non puoi utilizzare questa interfaccia!",
        "ja": "このインターフェースは使用できません！",
        "ko": "이 인터페이스를 사용할 수 없습니다!",
        "lt": "Jūs negalite naudoti šios sąsajos!",
        "nl": "Je kunt deze interface niet gebruiken!",
        "no": "Du kan ikke bruke dette grensesnittet!",
        "pl": "Nie możesz używać tego interfejsu!",
        "pt_BR": "Você não pode usar esta interface!",
        "ro": "Nu puteți folosi această interfață!",
        "ru": "Вы не можете использовать этот интерфейс!",
        "sv_SE": "Du kan inte använda detta gränssnitt!",
        "th": "คุณไม่สามารถใช้อินเทอร์เฟซนี้ได้!",
        "tr": "Bu arayüzü kullanamazsınız!",
        "uk": "Ви не можете використовувати цей інтерфейс!",
        "vi": "Bạn không thể sử dụng giao diện này!",
        "zh_CN": "您无法使用此界面！",
        "zh_TW": "您無法使用此介面！",
        "he_IL": "!אינך יכול להשתמש בממשק זה",
    },
    (None, "async"): {l: "async" for l in TARGET_LOCALES},
    (None, "Execute arbitrary code with Exec"): {
        "bg": "Изпълнение на произволен код с Exec",
        "cs": "Spuštění libovolného kódu pomocí Exec",
        "da": "Kør vilkårlig kode med Exec",
        "de": "Beliebigen Code mit Exec ausführen",
        "el": "Εκτέλεση αυθαίρετου κώδικα με Exec",
        "es_ES": "Ejecutar código arbitrario con Exec",
        "fi": "Suorita mielivaltaista koodia Exec-komennolla",
        "fr": "Exécuter du code arbitraire avec Exec",
        "hi": "Exec के साथ मनमाना कोड चलाएं",
        "hr": "Izvršite proizvoljni kod pomoću Exec",
        "hu": "Tetszőleges kód futtatása az Exec paranccsal",
        "id": "Jalankan kode arbitrer dengan Exec",
        "it": "Esegui codice arbitrario con Exec",
        "ja": "Execで任意のコードを実行する",
        "ko": "Exec로 임의의 코드 실행",
        "lt": "Vykdyti savavališką kodą su Exec",
        "nl": "Willekeurige code uitvoeren met Exec",
        "no": "Kjør vilkårlig kode med Exec",
        "pl": "Wykonaj dowolny kod za pomocą Exec",
        "pt_BR": "Executar código arbitrário com Exec",
        "ro": "Executați cod arbitrar cu Exec",
        "ru": "Выполнить произвольный код с помощью Exec",
        "sv_SE": "Kör godtycklig kod med Exec",
        "th": "รันโค้ดที่กำหนดเองด้วย Exec",
        "tr": "Exec ile rastgele kod çalıştır",
        "uk": "Виконати довільний код за допомогою Exec",
        "vi": "Chạy mã tùy ý với Exec",
        "zh_CN": "使用Exec执行任意代码",
        "zh_TW": "使用Exec執行任意程式碼",
        "he_IL": "הרצת קוד שרירותי עם Exec",
    },
    (None, "eval"): {l: "eval" for l in TARGET_LOCALES},
}

TOPGG_TRANSLATIONS = {
    ("button:vote|label", "Vote for me!"): {
        "bg": "Гласувайте за мен!",
        "cs": "Hlasujte pro mě!",
        "da": "Stem på mig!",
        "de": "Stimm für mich!",
        "el": "Ψηφίστε με!",
        "es_ES": "¡Vota por mí!",
        "fi": "Äänestä minua!",
        "fr": "Votez pour moi !",
        "hi": "मेरे लिए वोट करें!",
        "hr": "Glasajte za mene!",
        "hu": "Szavazz rám!",
        "id": "Vote untuk saya!",
        "it": "Vota per me!",
        "ja": "投票してください！",
        "ko": "투표해 주세요!",
        "lt": "Balsuokite už mane!",
        "nl": "Stem op mij!",
        "no": "Stem på meg!",
        "pl": "Zagłosuj na mnie!",
        "pt_BR": "Vote em mim!",
        "ro": "Votați pentru mine!",
        "ru": "Проголосуйте за меня!",
        "sv_SE": "Rösta på mig!",
        "th": "โหวตให้ฉัน!",
        "tr": "Bana oy verin!",
        "uk": "Проголосуйте за мене!",
        "vi": "Bình chọn cho tôi!",
        "zh_CN": "为我投票！",
        "zh_TW": "為我投票！",
        "he_IL": "!הצביעו בעדי",
    },
    ("embed:voting_thanks|title", "Thank you for supporting me on Top.gg! {yay}"): {
        "bg": "Благодаря, че ме подкрепяте в Top.gg! {yay}",
        "cs": "Děkuji za podporu na Top.gg! {yay}",
        "da": "Tak fordi du støtter mig på Top.gg! {yay}",
        "de": "Danke für deine Unterstützung auf Top.gg! {yay}",
        "el": "Ευχαριστώ που με υποστηρίζετε στο Top.gg! {yay}",
        "es_ES": "¡Gracias por apoyarme en Top.gg! {yay}",
        "fi": "Kiitos tuestasi Top.gg:ssä! {yay}",
        "fr": "Merci de me soutenir sur Top.gg ! {yay}",
        "hi": "Top.gg पर मुझे सपोर्ट करने के लिए धन्यवाद! {yay}",
        "hr": "Hvala na podršci na Top.gg! {yay}",
        "hu": "Köszönöm a támogatást a Top.gg-n! {yay}",
        "id": "Terima kasih telah mendukung saya di Top.gg! {yay}",
        "it": "Grazie per il supporto su Top.gg! {yay}",
        "ja": "Top.ggでの応援ありがとうございます！ {yay}",
        "ko": "Top.gg에서 응원해 주셔서 감사합니다! {yay}",
        "lt": "Ačiū, kad palaikote mane Top.gg! {yay}",
        "nl": "Bedankt voor je steun op Top.gg! {yay}",
        "no": "Takk for at du støtter meg på Top.gg! {yay}",
        "pl": "Dziękuję za wsparcie na Top.gg! {yay}",
        "pt_BR": "Obrigado por me apoiar no Top.gg! {yay}",
        "ro": "Mulțumesc pentru susținerea pe Top.gg! {yay}",
        "ru": "Спасибо за поддержку на Top.gg! {yay}",
        "sv_SE": "Tack för ditt stöd på Top.gg! {yay}",
        "th": "ขอบคุณที่สนับสนุนฉันบน Top.gg! {yay}",
        "tr": "Top.gg'de beni desteklediğiniz için teşekkürler! {yay}",
        "uk": "Дякую за підтримку на Top.gg! {yay}",
        "vi": "Cảm ơn bạn đã ủng hộ tôi trên Top.gg! {yay}",
        "zh_CN": "感谢您在Top.gg上支持我！{yay}",
        "zh_TW": "感謝您在Top.gg上支持我！{yay}",
        "he_IL": "תודה שתמכת בי ב-Top.gg! {yay}",
    },
    ("embed:voting_thanks|desc", "Thank you for supporting us, enjoy your LionCoins boost!"): {
        "bg": "Благодарим за подкрепата, наслаждавайте се на бонуса за LionCoins!",
        "cs": "Děkujeme za podporu, užijte si bonus LionCoins!",
        "da": "Tak for din støtte, nyd dit LionCoins-boost!",
        "de": "Danke für deine Unterstützung, genieße deinen LionCoins-Boost!",
        "el": "Ευχαριστούμε για την υποστήριξη, απολαύστε το μπόνους LionCoins!",
        "es_ES": "¡Gracias por apoyarnos, disfruta tu bonus de LionCoins!",
        "fi": "Kiitos tuestasi, nauti LionCoins-bonuksestasi!",
        "fr": "Merci pour votre soutien, profitez de votre bonus de LionCoins !",
        "hi": "सपोर्ट करने के लिए धन्यवाद, अपने LionCoins बूस्ट का आनंद लें!",
        "hr": "Hvala na podršci, uživajte u LionCoins bonusu!",
        "hu": "Köszönjük a támogatást, élvezd a LionCoins bónuszt!",
        "id": "Terima kasih atas dukungannya, nikmati bonus LionCoins-mu!",
        "it": "Grazie per il supporto, goditi il tuo bonus LionCoins!",
        "ja": "応援ありがとうございます、LionCoinsブーストをお楽しみください！",
        "ko": "응원해 주셔서 감사합니다, LionCoins 부스트를 즐기세요!",
        "lt": "Dėkojame už palaikymą, mėgaukitės LionCoins bonusu!",
        "nl": "Bedankt voor je steun, geniet van je LionCoins-boost!",
        "no": "Takk for støtten, nyt din LionCoins-boost!",
        "pl": "Dziękujemy za wsparcie, ciesz się bonusem LionCoins!",
        "pt_BR": "Obrigado pelo apoio, aproveite o bônus de LionCoins!",
        "ro": "Mulțumim pentru susținere, bucură-te de bonusul LionCoins!",
        "ru": "Спасибо за поддержку, наслаждайтесь бонусом LionCoins!",
        "sv_SE": "Tack för ditt stöd, njut av din LionCoins-bonus!",
        "th": "ขอบคุณสำหรับการสนับสนุน เพลิดเพลินกับโบนัส LionCoins ของคุณ!",
        "tr": "Desteğiniz için teşekkürler, LionCoins bonusunuzun tadını çıkarın!",
        "uk": "Дякуємо за підтримку, насолоджуйтесь бонусом LionCoins!",
        "vi": "Cảm ơn bạn đã ủng hộ, hãy tận hưởng phần thưởng LionCoins!",
        "zh_CN": "感谢您的支持，享受您的LionCoins加成！",
        "zh_TW": "感謝您的支持，享受您的LionCoins加成！",
        "he_IL": "תודה על התמיכה, תהנו מבונוס ה-LionCoins!",
    },
}

TIMER_GUI_TRANSLATIONS = {
    ("skin:timer|field:date_text", "Use /now to show what you are working on!"): {
        "bg": "Използвайте /now, за да покажете над какво работите!",
        "cs": "Použijte /now k zobrazení toho, na čem pracujete!",
        "da": "Brug /now for at vise hvad du arbejder på!",
        "de": "Benutze /now, um zu zeigen, woran du arbeitest!",
        "el": "Χρησιμοποίησε /now για να δείξεις σε τι δουλεύεις!",
        "es_ES": "¡Usa /now para mostrar en qué estás trabajando!",
        "fi": "Käytä /now näyttääksesi mitä teet!",
        "fr": "Utilisez /now pour montrer sur quoi vous travaillez !",
        "hi": "आप किस पर काम कर रहे हैं यह दिखाने के लिए /now का उपयोग करें!",
        "hr": "Koristite /now da pokažete na čemu radite!",
        "hu": "Használd a /now parancsot, hogy megmutasd, min dolgozol!",
        "id": "Gunakan /now untuk menampilkan apa yang sedang kamu kerjakan!",
        "it": "Usa /now per mostrare su cosa stai lavorando!",
        "ja": "/nowを使って今取り組んでいることを表示しよう！",
        "ko": "/now를 사용하여 현재 작업 중인 내용을 표시하세요!",
        "lt": "Naudokite /now, kad parodytumėte, ką darote!",
        "nl": "Gebruik /now om te laten zien waar je aan werkt!",
        "no": "Bruk /now for å vise hva du jobber med!",
        "pl": "Użyj /now, aby pokazać, nad czym pracujesz!",
        "pt_BR": "Use /now para mostrar no que você está trabalhando!",
        "ro": "Folosește /now pentru a arăta la ce lucrezi!",
        "ru": "Используйте /now, чтобы показать, над чем вы работаете!",
        "sv_SE": "Använd /now för att visa vad du jobbar med!",
        "th": "ใช้ /now เพื่อแสดงสิ่งที่คุณกำลังทำอยู่!",
        "tr": "Ne üzerinde çalıştığını göstermek için /now kullan!",
        "uk": "Використовуйте /now, щоб показати, над чим ви працюєте!",
        "vi": "Sử dụng /now để hiển thị những gì bạn đang làm!",
        "zh_CN": "使用 /now 来展示你正在做什么！",
        "zh_TW": "使用 /now 來展示你正在做什麼！",
        "he_IL": "!השתמשו ב-/now כדי להראות על מה אתם עובדים",
    },
    ("skin:timer|stage:focus|field:stage_text", "FOCUS"): {
        "bg": "ФОКУС", "cs": "SOUSTŘEDĚNÍ", "da": "FOKUS", "de": "FOKUS",
        "el": "ΕΣΤΙΑΣΗ", "es_ES": "ENFOQUE", "fi": "KESKITTYMINEN", "fr": "CONCENTRATION",
        "hi": "फोकस", "hr": "FOKUS", "hu": "FÓKUSZ", "id": "FOKUS",
        "it": "CONCENTRAZIONE", "ja": "集中", "ko": "집중", "lt": "SUSIKAUPIMAS",
        "nl": "FOCUS", "no": "FOKUS", "pl": "SKUPIENIE", "pt_BR": "FOCO",
        "ro": "CONCENTRARE", "ru": "ФОКУС", "sv_SE": "FOKUS", "th": "โฟกัส",
        "tr": "ODAKLANMA", "uk": "ФОКУС", "vi": "TẬP TRUNG",
        "zh_CN": "专注", "zh_TW": "專注", "he_IL": "ריכוז",
    },
    ("skin:timer|stage:break|field:stage_text", "BREAK"): {
        "bg": "ПОЧИВКА", "cs": "PŘESTÁVKA", "da": "PAUSE", "de": "PAUSE",
        "el": "ΔΙΑΛΕΙΜΜΑ", "es_ES": "DESCANSO", "fi": "TAUKO", "fr": "PAUSE",
        "hi": "ब्रेक", "hr": "PAUZA", "hu": "SZÜNET", "id": "ISTIRAHAT",
        "it": "PAUSA", "ja": "休憩", "ko": "휴식", "lt": "PERTRAUKA",
        "nl": "PAUZE", "no": "PAUSE", "pl": "PRZERWA", "pt_BR": "PAUSA",
        "ro": "PAUZĂ", "ru": "ПЕРЕРЫВ", "sv_SE": "PAUS", "th": "พัก",
        "tr": "MOLA", "uk": "ПЕРЕРВА", "vi": "NGHỈ",
        "zh_CN": "休息", "zh_TW": "休息", "he_IL": "הפסקה",
    },
}

CORE_CONFIG_TRANSLATIONS = {
    ("group:config", "config"): {l: "config" for l in TARGET_LOCALES},
    ("group:config|desc", "View and adjust moderation-level configuration."): {
        "bg": "Преглед и настройка на конфигурацията на ниво модератор.",
        "cs": "Zobrazení a úprava konfigurace na úrovni moderátora.",
        "da": "Se og juster konfiguration på moderatorniveau.",
        "de": "Moderator-Konfiguration anzeigen und anpassen.",
        "el": "Προβολή και ρύθμιση διαμόρφωσης επιπέδου συντονιστή.",
        "es_ES": "Ver y ajustar la configuración a nivel de moderador.",
        "fi": "Näytä ja muokkaa moderaattoritason asetuksia.",
        "fr": "Afficher et ajuster la configuration au niveau modérateur.",
        "hi": "मॉडरेटर-स्तरीय कॉन्फ़िगरेशन देखें और समायोजित करें।",
        "hr": "Pregledajte i prilagodite konfiguraciju na razini moderatora.",
        "hu": "Moderátori szintű konfiguráció megtekintése és módosítása.",
        "id": "Lihat dan sesuaikan konfigurasi tingkat moderator.",
        "it": "Visualizza e modifica la configurazione a livello moderatore.",
        "ja": "モデレーターレベルの設定を表示・調整する。",
        "ko": "관리자 수준의 설정을 확인하고 조정합니다.",
        "lt": "Peržiūrėkite ir koreguokite moderatoriaus lygio konfigūraciją.",
        "nl": "Moderatorconfiguratie bekijken en aanpassen.",
        "no": "Se og juster konfigurasjon på moderatornivå.",
        "pl": "Przeglądaj i dostosuj konfigurację na poziomie moderatora.",
        "pt_BR": "Visualizar e ajustar a configuração no nível de moderador.",
        "ro": "Vizualizați și ajustați configurația la nivel de moderator.",
        "ru": "Просмотр и настройка конфигурации на уровне модератора.",
        "sv_SE": "Visa och justera moderatornivåkonfiguration.",
        "th": "ดูและปรับการตั้งค่าระดับผู้ดูแล",
        "tr": "Moderatör seviyesi yapılandırmasını görüntüle ve ayarla.",
        "uk": "Перегляд і налаштування конфігурації рівня модератора.",
        "vi": "Xem và điều chỉnh cấu hình cấp quản trị viên.",
        "zh_CN": "查看和调整版主级别配置。",
        "zh_TW": "查看和調整版主級別配置。",
        "he_IL": "הצגה והתאמה של תצורה ברמת מנהל.",
    },
    ("group:admin", "admin"): {l: "admin" for l in TARGET_LOCALES},
    ("group:admin|desc", "Administrative commands."): {
        "bg": "Административни команди.",
        "cs": "Administrativní příkazy.",
        "da": "Administrative kommandoer.",
        "de": "Administrative Befehle.",
        "el": "Διοικητικές εντολές.",
        "es_ES": "Comandos administrativos.",
        "fi": "Hallinnolliset komennot.",
        "fr": "Commandes administratives.",
        "hi": "प्रशासनिक कमांड।",
        "hr": "Administrativne naredbe.",
        "hu": "Adminisztratív parancsok.",
        "id": "Perintah administratif.",
        "it": "Comandi amministrativi.",
        "ja": "管理コマンド。",
        "ko": "관리 명령어.",
        "lt": "Administracinės komandos.",
        "nl": "Administratieve commando's.",
        "no": "Administrative kommandoer.",
        "pl": "Komendy administracyjne.",
        "pt_BR": "Comandos administrativos.",
        "ro": "Comenzi administrative.",
        "ru": "Административные команды.",
        "sv_SE": "Administrativa kommandon.",
        "th": "คำสั่งผู้ดูแลระบบ",
        "tr": "Yönetim komutları.",
        "uk": "Адміністративні команди.",
        "vi": "Các lệnh quản trị.",
        "zh_CN": "管理命令。",
        "zh_TW": "管理命令。",
        "he_IL": "פקודות ניהול.",
    },
    ("group:admin_config", "config"): {l: "config" for l in TARGET_LOCALES},
    ("group:admin_config|desc", "View and adjust admin-level configuration."): {
        "bg": "Преглед и настройка на конфигурацията на ниво администратор.",
        "cs": "Zobrazení a úprava konfigurace na úrovni administrátora.",
        "da": "Se og juster konfiguration på administratorniveau.",
        "de": "Administrator-Konfiguration anzeigen und anpassen.",
        "el": "Προβολή και ρύθμιση διαμόρφωσης επιπέδου διαχειριστή.",
        "es_ES": "Ver y ajustar la configuración a nivel de administrador.",
        "fi": "Näytä ja muokkaa ylläpitäjätason asetuksia.",
        "fr": "Afficher et ajuster la configuration au niveau administrateur.",
        "hi": "व्यवस्थापक-स्तरीय कॉन्फ़िगरेशन देखें और समायोजित करें।",
        "hr": "Pregledajte i prilagodite konfiguraciju na razini administratora.",
        "hu": "Adminisztrátori szintű konfiguráció megtekintése és módosítása.",
        "id": "Lihat dan sesuaikan konfigurasi tingkat administrator.",
        "it": "Visualizza e modifica la configurazione a livello amministratore.",
        "ja": "管理者レベルの設定を表示・調整する。",
        "ko": "관리자 수준의 설정을 확인하고 조정합니다.",
        "lt": "Peržiūrėkite ir koreguokite administratoriaus lygio konfigūraciją.",
        "nl": "Administratorconfiguratie bekijken en aanpassen.",
        "no": "Se og juster konfigurasjon på administratornivå.",
        "pl": "Przeglądaj i dostosuj konfigurację na poziomie administratora.",
        "pt_BR": "Visualizar e ajustar a configuração no nível de administrador.",
        "ro": "Vizualizați și ajustați configurația la nivel de administrator.",
        "ru": "Просмотр и настройка конфигурации на уровне администратора.",
        "sv_SE": "Visa och justera administratörsnivåkonfiguration.",
        "th": "ดูและปรับการตั้งค่าระดับผู้ดูแลระบบ",
        "tr": "Yönetici seviyesi yapılandırmasını görüntüle ve ayarla.",
        "uk": "Перегляд і налаштування конфігурації рівня адміністратора.",
        "vi": "Xem và điều chỉnh cấu hình cấp quản trị viên.",
        "zh_CN": "查看和调整管理员级别配置。",
        "zh_TW": "查看和調整管理員級別配置。",
        "he_IL": "הצגה והתאמה של תצורה ברמת מנהל מערכת.",
    },
}

PROFILE_GUI_TRANSLATIONS = {
    ("skin:profile|header:profile", "PROFILE"): {
        "bg": "ПРОФИЛ", "cs": "PROFIL", "da": "PROFIL", "de": "PROFIL",
        "el": "ΠΡΟΦΙΛ", "es_ES": "PERFIL", "fi": "PROFIILI", "fr": "PROFIL",
        "hi": "प्रोफ़ाइल", "hr": "PROFIL", "hu": "PROFIL", "id": "PROFIL",
        "it": "PROFILO", "ja": "プロフィール", "ko": "프로필", "lt": "PROFILIS",
        "nl": "PROFIEL", "no": "PROFIL", "pl": "PROFIL", "pt_BR": "PERFIL",
        "ro": "PROFIL", "ru": "ПРОФИЛЬ", "sv_SE": "PROFIL", "th": "โปรไฟล์",
        "tr": "PROFİL", "uk": "ПРОФІЛЬ", "vi": "HỒ SƠ",
        "zh_CN": "个人资料", "zh_TW": "個人資料", "he_IL": "פרופיל",
    },
    ("skin:profile|header:achievements", "ACHIEVEMENTS"): {
        "bg": "ПОСТИЖЕНИЯ", "cs": "ÚSPĚCHY", "da": "PRÆSTATIONER", "de": "ERFOLGE",
        "el": "ΕΠΙΤΕΎΓΜΑΤΑ", "es_ES": "LOGROS", "fi": "SAAVUTUKSET", "fr": "RÉALISATIONS",
        "hi": "उपलब्धियाँ", "hr": "POSTIGNUĆA", "hu": "EREDMÉNYEK", "id": "PENCAPAIAN",
        "it": "TRAGUARDI", "ja": "実績", "ko": "업적", "lt": "PASIEKIMAI",
        "nl": "PRESTATIES", "no": "PRESTASJONER", "pl": "OSIĄGNIĘCIA", "pt_BR": "CONQUISTAS",
        "ro": "REALIZĂRI", "ru": "ДОСТИЖЕНИЯ", "sv_SE": "PRESTATIONER", "th": "ความสำเร็จ",
        "tr": "BAŞARILAR", "uk": "ДОСЯГНЕННЯ", "vi": "THÀNH TÍCH",
        "zh_CN": "成就", "zh_TW": "成就", "he_IL": "הישגים",
    },
    ("skin:profile|field:rank_unranked_text", "UNRANKED"): {
        "bg": "БЕЗ РАНГ", "cs": "BEZ HODNOSTI", "da": "URANGERET", "de": "OHNE RANG",
        "el": "ΑΚΑΤΑΤΑΞΤΟΣ", "es_ES": "SIN RANGO", "fi": "EI SIJOITUSTA", "fr": "NON CLASSÉ",
        "hi": "अवर्गीकृत", "hr": "BEZ RANGA", "hu": "RANGSOROLATLAN", "id": "TIDAK BERPERINGKAT",
        "it": "SENZA GRADO", "ja": "ランクなし", "ko": "미등급", "lt": "BE RANGO",
        "nl": "GEEN RANG", "no": "URANGERT", "pl": "BEZ RANGI", "pt_BR": "SEM CLASSIFICAÇÃO",
        "ro": "NECLASIFICAT", "ru": "БЕЗ РАНГА", "sv_SE": "ORANKAD", "th": "ยังไม่มีแรงค์",
        "tr": "RÜTBESIZ", "uk": "БЕЗ РАНГУ", "vi": "CHƯA XẾP HẠNG",
        "zh_CN": "未排名", "zh_TW": "未排名", "he_IL": "ללא דירוג",
    },
    ("skin:profile|field:rank_nextrank_text", "NEXT RANK: {name} {rangestr}"): {
        "bg": "СЛЕДВАЩ РАНГ: {name} {rangestr}",
        "cs": "DALŠÍ HODNOST: {name} {rangestr}",
        "da": "NÆSTE RANG: {name} {rangestr}",
        "de": "NÄCHSTER RANG: {name} {rangestr}",
        "el": "ΕΠΟΜΕΝΗ ΤΑΞΗ: {name} {rangestr}",
        "es_ES": "SIGUIENTE RANGO: {name} {rangestr}",
        "fi": "SEURAAVA TASO: {name} {rangestr}",
        "fr": "PROCHAIN RANG : {name} {rangestr}",
        "hi": "अगला रैंक: {name} {rangestr}",
        "hr": "SLJEDEĆI RANG: {name} {rangestr}",
        "hu": "KÖVETKEZŐ RANG: {name} {rangestr}",
        "id": "PERINGKAT BERIKUTNYA: {name} {rangestr}",
        "it": "PROSSIMO GRADO: {name} {rangestr}",
        "ja": "次のランク: {name} {rangestr}",
        "ko": "다음 등급: {name} {rangestr}",
        "lt": "KITAS RANGAS: {name} {rangestr}",
        "nl": "VOLGENDE RANG: {name} {rangestr}",
        "no": "NESTE RANG: {name} {rangestr}",
        "pl": "NASTĘPNA RANGA: {name} {rangestr}",
        "pt_BR": "PRÓXIMO RANKING: {name} {rangestr}",
        "ro": "URMĂTORUL RANG: {name} {rangestr}",
        "ru": "СЛЕДУЮЩИЙ РАНГ: {name} {rangestr}",
        "sv_SE": "NÄSTA RANG: {name} {rangestr}",
        "th": "แรงค์ถัดไป: {name} {rangestr}",
        "tr": "SONRAKİ RÜTBE: {name} {rangestr}",
        "uk": "НАСТУПНИЙ РАНГ: {name} {rangestr}",
        "vi": "HẠNG TIẾP THEO: {name} {rangestr}",
        "zh_CN": "下一等级: {name} {rangestr}",
        "zh_TW": "下一等級: {name} {rangestr}",
        "he_IL": "דירוג הבא: {name} {rangestr}",
    },
    ("skin:profile|field:rank_noranks_text", "NO RANKS AVAILABLE"): {
        "bg": "НЯМА НАЛИЧНИ РАНГОВЕ", "cs": "ŽÁDNÉ DOSTUPNÉ HODNOSTI",
        "da": "INGEN RANGER TILGÆNGELIGE", "de": "KEINE RÄNGE VERFÜGBAR",
        "el": "ΔΕΝ ΥΠΑΡΧΟΥΝ ΔΙΑΘΕΣΙΜΕΣ ΤΑΞΕΙΣ", "es_ES": "NO HAY RANGOS DISPONIBLES",
        "fi": "EI TASOJA SAATAVILLA", "fr": "AUCUN RANG DISPONIBLE",
        "hi": "कोई रैंक उपलब्ध नहीं", "hr": "NEMA DOSTUPNIH RANGOVA",
        "hu": "NINCSENEK ELÉRHETŐ RANGOK", "id": "TIDAK ADA PERINGKAT TERSEDIA",
        "it": "NESSUN GRADO DISPONIBILE", "ja": "ランクなし",
        "ko": "사용 가능한 등급 없음", "lt": "RANGŲ NĖRA",
        "nl": "GEEN RANGEN BESCHIKBAAR", "no": "INGEN RANGER TILGJENGELIG",
        "pl": "BRAK DOSTĘPNYCH RANG", "pt_BR": "NENHUM RANKING DISPONÍVEL",
        "ro": "NU SUNT RANGURI DISPONIBILE", "ru": "НЕТ ДОСТУПНЫХ РАНГОВ",
        "sv_SE": "INGA RANGER TILLGÄNGLIGA", "th": "ไม่มีแรงค์ที่ใช้ได้",
        "tr": "MEVCUT RÜTBE YOK", "uk": "НЕМАЄ ДОСТУПНИХ РАНГІВ",
        "vi": "KHÔNG CÓ HẠNG NÀO", "zh_CN": "暂无可用等级",
        "zh_TW": "暫無可用等級", "he_IL": "אין דירוגים זמינים",
    },
    ("skin:profile|field:rank_maxrank_text", "YOU HAVE REACHED THE MAXIMUM RANK"): {
        "bg": "ДОСТИГНАХТЕ МАКСИМАЛНИЯ РАНГ",
        "cs": "DOSÁHLI JSTE MAXIMÁLNÍ HODNOSTI",
        "da": "DU HAR NÅET DEN HØJESTE RANG",
        "de": "DU HAST DEN HÖCHSTEN RANG ERREICHT",
        "el": "ΕΧΕΤΕ ΦΤΑΣΕΙ ΤΗΝ ΑΝΩΤΑΤΗ ΤΑΞΗ",
        "es_ES": "HAS ALCANZADO EL RANGO MÁXIMO",
        "fi": "OLET SAAVUTTANUT KORKEIMMAN TASON",
        "fr": "VOUS AVEZ ATTEINT LE RANG MAXIMUM",
        "hi": "आपने अधिकतम रैंक प्राप्त कर लिया है",
        "hr": "DOSTIGLI STE MAKSIMALNI RANG",
        "hu": "ELÉRTED A LEGMAGASABB RANGOT",
        "id": "ANDA TELAH MENCAPAI PERINGKAT MAKSIMUM",
        "it": "HAI RAGGIUNTO IL GRADO MASSIMO",
        "ja": "最高ランクに到達しました",
        "ko": "최고 등급에 도달했습니다",
        "lt": "PASIEKĖTE AUKŠČIAUSIĄ RANGĄ",
        "nl": "JE HEBT DE HOOGSTE RANG BEREIKT",
        "no": "DU HAR NÅDD HØYESTE RANG",
        "pl": "OSIĄGNĄŁEŚ NAJWYŻSZĄ RANGĘ",
        "pt_BR": "VOCÊ ATINGIU O RANKING MÁXIMO",
        "ro": "AȚI ATINS RANGUL MAXIM",
        "ru": "ВЫ ДОСТИГЛИ МАКСИМАЛЬНОГО РАНГА",
        "sv_SE": "DU HAR NÅTT HÖGSTA RANG",
        "th": "คุณถึงแรงค์สูงสุดแล้ว",
        "tr": "EN YÜKSEK RÜTBEYE ULAŞTINIZ",
        "uk": "ВИ ДОСЯГЛИ МАКСИМАЛЬНОГО РАНГУ",
        "vi": "BẠN ĐÃ ĐẠT HẠNG CAO NHẤT",
        "zh_CN": "您已达到最高等级",
        "zh_TW": "您已達到最高等級",
        "he_IL": "הגעת לדירוג המקסימלי",
    },
}


def run_domain(domain, ai_translations):
    """Generate .po files for a domain, merging salvaged + existing + AI translations."""
    pot_path = os.path.join(TEMPLATES_DIR, f"{domain}.pot")
    entries = parse_pot(pot_path)
    print(f"  {domain}: {len(entries)} strings")

    salvaged = load_salvaged(domain)
    existing = load_existing_translations(domain)

    merged = {}
    for key, locale_map in salvaged.items():
        merged[key] = locale_map.copy()
    for key, locale_map in ai_translations.items():
        if key not in merged:
            merged[key] = {}
        for locale, text in locale_map.items():
            if locale not in merged[key]:
                merged[key][locale] = text

    count = write_po_files(domain, entries, merged, existing_map=existing)
    print(f"    -> wrote {count} .po files")


def main():
    print("=== Generating tiny domain translations ===")
    run_domain("base", BASE_TRANSLATIONS)
    run_domain("topgg", TOPGG_TRANSLATIONS)
    run_domain("timer-gui", TIMER_GUI_TRANSLATIONS)
    run_domain("core_config", CORE_CONFIG_TRANSLATIONS)
    run_domain("profile-gui", PROFILE_GUI_TRANSLATIONS)
    print("Done!")


if __name__ == '__main__':
    main()
