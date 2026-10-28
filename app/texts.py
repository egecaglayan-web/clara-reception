from app.config import DOCTORS


TEXT = {
    "info": ("Klinik bilgilerimiz:", "Our clinic information:", "معلومات عيادتنا:"),
    "date_format": ("Tercih ettiğiniz günü YYYY-MM-DD ve saati HH:MM biçiminde yazar mısınız?",
                    "Please send your preferred date as YYYY-MM-DD and time as HH:MM.",
                    "يرجى إرسال التاريخ المفضل بصيغة YYYY-MM-DD والوقت بصيغة HH:MM."),
    "missing": ("Lütfen şu bilgileri tek yanıtta paylaşın: ", "Please send these details in one reply: ", "يرجى إرسال المعلومات التالية في رد واحد: "),
    "full_name": ("adınız ve soyadınız", "your full name", "الاسم الكامل"),
    "doctor": ("doktor veya uzmanlık", "doctor or specialty", "الطبيب أو التخصص"),
    "offers": ("Kontrol ettiğim uygun saatler aşağıda. Lütfen tek bir seçeneği açıkça seçin. Henüz randevu oluşturulmadı.",
               "These times were checked and are available. Please explicitly choose one option. No appointment has been booked yet.",
               "تم التحقق من توفر الأوقات التالية. يرجى اختيار موعد واحد بوضوح. لم يتم حجز موعد بعد."),
    "booked": ("Randevunuz takvimden doğrulandı ve oluşturuldu.", "Your appointment has been booked and verified in the calendar.", "تم حجز موعدك والتحقق منه في التقويم."),
    "rescheduled": ("Randevunuzun yeni saati takvimden doğrulandı.", "Your rescheduled appointment has been verified in the calendar.", "تم التحقق من الموعد الجديد في التقويم."),
    "cancelled": ("Seçtiğiniz randevunun iptali takvim tarafından doğrulandı.", "The calendar confirmed the cancellation of your selected appointment.", "أكد التقويم إلغاء الموعد الذي اخترته."),
    "which": ("Yaklaşan randevularınız aşağıda. Hangisi için işlem yapmak istediğinizi randevu numarasıyla belirtin.",
              "Your upcoming appointments are listed below. Please identify one by its appointment number.",
              "مواعيدك القادمة أدناه. يرجى تحديد الموعد المطلوب باستخدام رقمه."),
    "confirm_cancel": ("Aşağıdaki randevuyu iptal etmek istediğinizi açıkça onaylar mısınız?", "Please explicitly confirm that you want to cancel this appointment.", "يرجى التأكيد بوضوح أنك تريد إلغاء هذا الموعد."),
    "no_appointments": ("Bu e-posta adresine ait yaklaşan randevu bulunamadı.", "No upcoming appointments were found for your email address.", "لم يتم العثور على مواعيد قادمة لعنوان بريدك الإلكتروني."),
    "duplicate": ("Bu doktorla aynı gün zaten bir randevunuz var. İsterseniz mevcut randevunuzu değiştirebiliriz.",
                  "You already have an appointment with this doctor on that day. You can request to reschedule it.",
                  "لديك موعد مع هذا الطبيب في اليوم نفسه بالفعل. يمكنك طلب تغيير الموعد الحالي."),
    "unavailable": ("Seçtiğiniz saat artık uygun değil. Yeni seçenekler istemek için tercih ettiğiniz günü paylaşın.",
                    "Your selected time is no longer available. Please send your preferred day for new options.",
                    "الوقت الذي اخترته لم يعد متاحا. يرجى إرسال اليوم المفضل للحصول على خيارات جديدة."),
    "range": ("Randevular yarından itibaren 30 gün içinde, hafta içi 09:00–12:00 ve 13:00–17:00 arasında, 30 dakikalıktır. Lütfen uygun bir gün/saat belirtin.",
              "Appointments are 30 minutes, from tomorrow through the next 30 days, weekdays 09:00–12:00 and 13:00–17:00. Please choose a valid day/time.",
              "المواعيد 30 دقيقة من الغد وحتى 30 يوما، أيام العمل 09:00–12:00 و13:00–17:00. يرجى اختيار يوم ووقت مناسبين."),
    "handoff": ("Talebinizi resepsiyon ekibine iletiyorum. Bir ekip üyesi yanıt verecek.", "I am forwarding your request to reception. A team member will reply.", "أحيل طلبك إلى فريق الاستقبال. سيرد عليك أحد أعضاء الفريق."),
    "error": ("Üzgünüm, işleminizi doğrulayamadım. Takvimde değişiklik olmuş olabilir; lütfen aynı işlemi tekrar göndermeyin. Ekibimiz kontrol edip yanıt verecek.",
              "Sorry, I could not verify the outcome. The calendar may have changed; please do not repeat the request. Our team will check and follow up.",
              "عذرا، تعذر التحقق من نتيجة العملية. ربما تغير التقويم؛ يرجى عدم تكرار الطلب. سيتحقق فريقنا ويتابع معك."),
    "already": ("Teşekkürler, mesajınızı mevcut talebinize ekledim.", "Thank you. Your message has been added to your existing request.", "شكرا. تمت إضافة رسالتك إلى طلبك الحالي."),
    "privacy": ("Yalnızca bu e-posta adresine ait randevular hakkında yardımcı olabilirim. Başka kişilerin randevu bilgilerini paylaşamam veya değiştiremem.",
                "I can only help with appointments belonging to your email address. I cannot share or change another person's appointment details.",
                "يمكنني المساعدة فقط في المواعيد المرتبطة ببريدك الإلكتروني. لا يمكنني مشاركة أو تغيير تفاصيل مواعيد الآخرين."),
    "clarify": ("Randevu almak, değiştirmek, iptal etmek veya klinik bilgisi öğrenmek seçeneklerinden hangisi için yazıyorsunuz?",
                "Would you like to book, reschedule, cancel an appointment, or ask for clinic information?",
                "هل ترغب في حجز موعد أو تغييره أو إلغائه أم معرفة معلومات عن العيادة؟"),
    "emergency": ("Lütfen hemen 112 acil yardım hattını arayın. Buradan tıbbi değerlendirme yapamam.",
                  "Please call 112 emergency services immediately. I cannot provide a medical assessment here.",
                  "يرجى الاتصال بخدمات الطوارئ على 112 فورا. لا يمكنني تقديم تقييم طبي هنا."),
    "unverified": ("Gönderen doğrulanamadığı için randevu bilgilerinizi otomatik paylaşamıyor veya değiştiremiyorum.",
                   "I cannot automatically share or change appointments because the sender could not be verified.",
                   "لا يمكنني مشاركة أو تغيير المواعيد تلقائيا لتعذر التحقق من المرسل."),
}
INDEX = {"tr": 0, "en": 1, "ar": 2}
WEEKDAYS = {
    "tr": "Pazartesi Salı Çarşamba Perşembe Cuma Cumartesi Pazar".split(),
    "en": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(),
    "ar": "الاثنين الثلاثاء الأربعاء الخميس الجمعة السبت الأحد".split(),
}
MONTHS = {
    "tr": "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split(),
    "en": "January February March April May June July August September October November December".split(),
    "ar": "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر".split(),
}


def text(key, lang):
    return TEXT[key][INDEX[lang]]


def format_date(value, lang, zone):
    local = value.astimezone(zone)
    at = {"tr": "saat", "en": "at", "ar": "الساعة"}[lang]
    return f"{WEEKDAYS[lang][local.weekday()]}, {local.day} {MONTHS[lang][local.month - 1]} {local.year} {at} {local:%H:%M}"


def render(config, lang, kind, name=None, details=""):
    greeting = {"tr": "Merhaba", "en": "Hello", "ar": "مرحبا"}[lang]
    first = name.split()[0] if name and name.strip() else ""
    greeting += (" " + first if first else "") + ","
    content = text(kind, lang) + ("\n\n" + details if details else "")
    return (greeting + "\n\n" + content + "\n\nBest regards,\nClara – AI Receptionist\n"
            + config.clinic_name + " | " + config.clinic_phone)


def appointment_details(config, event, lang):
    return (DOCTORS[event.doctor][0] + " (" + DOCTORS[event.doctor][1] + ")\n"
            + format_date(event.start, lang, config.zone) + "\n" + config.clinic_address)


def clinic_info(config, lang):
    hours = {"tr": "Pazartesi–Cuma 09:00–17:00; öğle arası 12:00–13:00. Hafta sonu kapalı.",
             "en": "Monday–Friday 09:00–17:00; lunch 12:00–13:00. Closed on weekends.",
             "ar": "الاثنين–الجمعة 09:00–17:00؛ استراحة 12:00–13:00. مغلق في عطلة نهاية الأسبوع."}[lang]
    return "\n".join([config.clinic_name, hours, config.clinic_address, config.clinic_phone,
                      *[f"{name} — {specialty}" for name, specialty, _ in DOCTORS.values()]])
