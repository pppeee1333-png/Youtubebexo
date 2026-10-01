# YouTube Music Downloader Bot

بوت Telegram لتحميل الصوت من روابط YouTube وتحويله إلى MP3.

## المميزات
- YouTube فقط.
- يدعم youtube.com و youtu.be و Shorts و Live.
- اختيار جودة 64/128/192/320 kbps.
- رسائل أخطاء مفهومة للمستخدم.
- حذف الملفات المؤقتة تلقائياً.
- timeout وإعادة محاولات للتحميل.
- منع قوائم التشغيل.
- حد افتراضي 48MB لملف Telegram.
- جاهز للنشر على Railway.

## تشغيل محلياً
1. ثبّت Python 3.12 وFFmpeg.
2. انسخ `.env.example` إلى `.env`.
3. ضع BOT_TOKEN.
4. شغّل:
   `pip install -r requirements.txt`
5. ثم:
   `python main.py`

## Railway
1. ارفع المشروع إلى GitHub.
2. أنشئ مشروعاً جديداً في Railway واربط GitHub.
3. أضف Variable:
   `BOT_TOKEN=توكن_البوت`
4. Railway سيستخدم `nixpacks.toml` لتثبيت Python وFFmpeg وتشغيل البوت.
5. لا تحتاج إلى Web Server أو Port لأن البوت يستخدم Telegram Polling.

## ملاحظات
- البوت مخصص للمحتوى الذي يسمح المستخدم بتنزيله.
- بعض فيديوهات YouTube قد تكون غير قابلة للتحميل بسبب القيود أو حقوق المحتوى أو متطلبات تسجيل الدخول.
- Railway والـTelegram يفرضان حدوداً على الموارد وحجم الملفات؛ لذلك توجد حماية من الملفات الكبيرة والعمليات الطويلة.
