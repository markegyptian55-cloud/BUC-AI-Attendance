"""
Script to generate a professional Full HD tutorial video (with Edge TTS voiceover)
from screenshots in docs/evidence/.
"""

import os
import sys
from pathlib import Path

# Fix Windows console encoding for Arabic stdout
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr:
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display
import edge_tts
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

# Project paths
PROJECT_ROOT = Path(r"F:\projects\BUC AI Attendance")
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence"
TEMP_DIR = PROJECT_ROOT / "data" / "video_temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_VIDEO = EVIDENCE_DIR / "attendance_ai_tutorial.mp4"

# Color palette
COLOR_NAVY = (20, 33, 61)       # #14213D
COLOR_TERRACOTTA = (181, 87, 11) # #B5570B
COLOR_BG = (15, 23, 42)          # #0F172A
COLOR_BORDER = (51, 65, 85)      # #334155
COLOR_WHITE = (255, 255, 255)
COLOR_GOLD = (234, 179, 8)
COLOR_WARM_WHITE = (247, 245, 239)

FONT_PATH_TAHOMA = "C:/Windows/Fonts/tahoma.ttf"
FONT_PATH_BOLD = "C:/Windows/Fonts/tahomabd.ttf"
if not os.path.exists(FONT_PATH_BOLD):
    FONT_PATH_BOLD = FONT_PATH_TAHOMA

font_title = ImageFont.truetype(FONT_PATH_BOLD, 36)
font_badge = ImageFont.truetype(FONT_PATH_BOLD, 28)
font_subtitle = ImageFont.truetype(FONT_PATH_TAHOMA, 28)
font_brand = ImageFont.truetype(FONT_PATH_BOLD, 28)

SLIDES_CONFIG = [
    {
        "step": 1,
        "image": "05_login_admin.png",
        "title": "تسجيل الدخول إلى النظام",
        "subtitle": "تسجيل الدخول بحساب مسؤول النظام للوصول لكافة الصلاحيات",
        "narration": "مرحباً بكم في نظام التحضير الذكي للجامعات. نبدأ بتسجيل الدخول بحساب مسؤول النظام للوصول إلى لوحة الإدارة وإعداد المقررات والطلاب."
    },
    {
        "step": 2,
        "image": "01_enroll_faces_3poses_success.jpg",
        "title": "تسجيل البصمة البيومترية للوجه",
        "subtitle": "التقاط 3 وضعيات: أمامية، يسار، ويمين مع اجتياز فحص الجودة",
        "narration": "في صفحة تسجيل الوجوه، نقوم باختيار الطالب والتقاط ثلاث بصمات ثلاثية الأبعاد: الوجه من الأمام، ومن اليسار، ومن اليمين، ويتأكد النظام تلقائياً من وضوح الصورة والإضاءة."
    },
    {
        "step": 3,
        "image": "03_create_course_success.png",
        "title": "إنشاء المادة الدراسية",
        "subtitle": "إدخال كود المادة واسمها وتعيين أستاذ المادة المسؤول",
        "narration": "بعد ذلك، ننتقل لصفحة المقررات ونقوم بإنشاء المادة الدراسية، مثل مادة الرؤية الحاسوبية سي إس مية وواحد، وتعيين أستاذ المادة المسؤول عنها."
    },
    {
        "step": 4,
        "image": "09_manage_roster_add_student.png",
        "title": "الخطوة الأهم: إضافة الطلاب لكشف المادة",
        "subtitle": "ربط الطالب بكشف حضور المادة لمنع اعتباره وجهاً غير معروف",
        "narration": "هذه هي الخطوة الأساسية: من تبويب إدارة الكشف، نختار المادة ونحدد الطلاب المسجلين فيها ثم نضغط تحديث الكشف، لضمان مقارنة الوجوه بقائمة طلاب المحاضرة فقط."
    },
    {
        "step": 5,
        "image": "10_course_catalog_1_student.png",
        "title": "تأكيد تسجيل الطلاب في دليل المقررات",
        "subtitle": "التأكد من قيد الطلاب بنجاح وظهور عددهم في الكشف المعتمد",
        "narration": "الآن يظهر في دليل المقررات أن المادة تضم طالباً مقيداً، وأصبحت جاهزة تماماً لبدء المحاضرة وأخذ الحضور."
    },
    {
        "step": 6,
        "image": "06_take_attendance_camera_step.jpg",
        "title": "بدء تسجيل الحضور في المحاضرة",
        "subtitle": "فتح جلسة الحضور والتقاط صورة قاعة المحاضرات بالكاميرا",
        "narration": "في صفحة أخذ الحضور، يختار أستاذ المادة المقرر وتبدأ الكاميرا بالتقاط صورة القاعة للطلاب الحاضرين، ثم يضغط زر فحص الوجوه والتعرف الذكي."
    },
    {
        "step": 7,
        "image": "11_take_attendance_success_91pct.png",
        "title": "التعرف البيومتري الفوري بنجاح 91%",
        "subtitle": "مطابقة فورية وتحديد الطالب كحاضر مع شريط الثقة الأخضر",
        "narration": "في أقل من ثانية، يطابق النظام الوجه بدقة استثنائية بلغت واحداً وتسعين بالمئة، ويظهر الطالب فوراً كحاضر مع شريط الثقة ونسبة المطابقة العالية."
    },
    {
        "step": 8,
        "image": "08_take_attendance_done_zero.png",
        "title": "اعتماد كشف الحضور وإغلاق الجلسة",
        "subtitle": "مراجعة قائمة الحضور والضغط على حفظ الحضور لتثبيت السجلات",
        "narration": "يقوم المحاضر بمراجعة الكشف والضغط على زر حفظ الحضور، ليتم اعتماد السجلات وإغلاق جلسة المحاضرة بنجاح في قاعدة البيانات."
    },
    {
        "step": 9,
        "image": "12_dashboard_overview.png",
        "title": "متابعة المحاضرات عبر لوحة التحكم",
        "subtitle": "استعراض المقررات النشطة والجلسات المفتوحة وإجمالي الطلاب",
        "narration": "من لوحة التحكم الرئيسية، تتابع إدارة الكلية والمحاضرون إحصائيات المقررات والجلسات المنعقدة والطلاب المسجلين بكل سهولة وسرعة."
    },
    {
        "step": 10,
        "image": "13_attendance_reports.png",
        "title": "التقارير الشاملة وتصدير كشف الغياب",
        "subtitle": "متابعة نسب الحضور وتنبيهات الحرمان وتصدير ملف إكسيل",
        "narration": "وأخيراً في صفحة التقارير، يمكن متابعة نسب الحضور التراكمية، وتحديد الطلاب المعرضين للحرمان، وتحميل تقرير الحضور الرسمي بملف سي إس في بنقرة واحدة."
    }
]

def shape_arabic(text: str) -> str:
    """Helper to reshape and bidi-process Arabic text for Pillow."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def create_slide_frame(slide_idx: int, slide: dict) -> Path:
    """Renders a single 1920x1080 Full HD slide frame with branded header, footer and screenshot."""
    canvas_w, canvas_h = 1920, 1080
    frame = Image.new("RGB", (canvas_w, canvas_h), color=COLOR_BG)
    draw = ImageDraw.Draw(frame)

    # 1. Top Header Bar
    header_h = 110
    draw.rectangle([(0, 0), (canvas_w, header_h)], fill=COLOR_NAVY)
    # Accent terracotta line under header
    draw.rectangle([(0, header_h - 4), (canvas_w, header_h)], fill=COLOR_TERRACOTTA)

    # Left Branding
    brand_text = "🎓 BUC AI Attendance"
    draw.text((40, 38), brand_text, font=font_brand, fill=COLOR_GOLD)

    # Right Step Badge & Title
    step_num = slide["step"]
    badge_str = f"الخطوة {step_num:02d} من {len(SLIDES_CONFIG):02d}"
    badge_shaped = shape_arabic(badge_str)
    title_shaped = shape_arabic(slide["title"])

    # Draw title and badge
    full_header_title = f"{title_shaped}  |  {badge_shaped}"
    # Calculate width to right-align
    bbox = draw.textbbox((0, 0), full_header_title, font=font_title)
    text_w = bbox[2] - bbox[0]
    draw.text((canvas_w - 40 - text_w, 32), full_header_title, font=font_title, fill=COLOR_WHITE)

    # 2. Bottom Subtitle Bar
    footer_h = 100
    footer_y = canvas_h - footer_h
    draw.rectangle([(0, footer_y), (canvas_w, canvas_h)], fill=COLOR_NAVY)
    # Accent line above footer
    draw.rectangle([(0, footer_y), (canvas_w, footer_y + 3)], fill=COLOR_BORDER)

    sub_shaped = shape_arabic(slide["subtitle"])
    bbox_sub = draw.textbbox((0, 0), sub_shaped, font=font_subtitle)
    sub_w = bbox_sub[2] - bbox_sub[0]
    draw.text(((canvas_w - sub_w) // 2, footer_y + 30), sub_shaped, font=font_subtitle, fill=COLOR_WARM_WHITE)

    # 3. Main Screenshot
    img_path = EVIDENCE_DIR / slide["image"]
    if img_path.exists():
        screenshot = Image.open(img_path).convert("RGB")
        max_w = 1660
        max_h = footer_y - header_h - 40 # 980 - 110 - 40 = 830
        
        # Calculate aspect ratio
        scale = min(max_w / screenshot.width, max_h / screenshot.height)
        new_w = int(screenshot.width * scale)
        new_h = int(screenshot.height * scale)
        screenshot = screenshot.resize((new_w, new_h), Image.Resampling.LANCZOS)

        pos_x = (canvas_w - new_w) // 2
        pos_y = header_h + ((footer_y - header_h) - new_h) // 2

        # Draw screenshot border
        draw.rectangle(
            [(pos_x - 3, pos_y - 3), (pos_x + new_w + 2, pos_y + new_h + 2)],
            outline=COLOR_BORDER,
            width=3
        )
        frame.paste(screenshot, (pos_x, pos_y))
    else:
        print(f"Warning: image {img_path} not found!")

    out_path = TEMP_DIR / f"frame_{slide_idx:02d}.png"
    frame.save(out_path, quality=95)
    return out_path

async def generate_narration(slide_idx: int, slide: dict) -> Path:
    """Synthesizes high-quality Arabic neural voice for the slide."""
    audio_path = TEMP_DIR / f"audio_{slide_idx:02d}.mp3"
    voice = "ar-EG-ShakirNeural"
    communicate = edge_tts.Communicate(slide["narration"], voice=voice, rate="+5%")
    await communicate.save(str(audio_path))
    return audio_path

async def main():
    print("=" * 60)
    print("Attendance AI — Full HD Tutorial Video Generator")
    print("=" * 60)

    clips = []
    
    for idx, slide in enumerate(SLIDES_CONFIG):
        print(f"\n[Slide {slide['step']}/{len(SLIDES_CONFIG)}] {slide['title']}...")
        
        # 1. Render frame
        frame_path = create_slide_frame(idx, slide)
        print(f"  Frame rendered: {frame_path.name}")
        
        # 2. Synthesize audio
        audio_path = await generate_narration(idx, slide)
        print(f"  Audio generated: {audio_path.name}")
        
        # 3. Create moviepy clip
        audio_clip = AudioFileClip(str(audio_path))
        # Add 1.0 second pause after speech for visual comfort
        duration = audio_clip.duration + 1.2
        
        img_clip = ImageClip(str(frame_path)).with_duration(duration).with_audio(audio_clip)
        clips.append(img_clip)

    print("\nConcatenating all clips...")
    final_video = concatenate_videoclips(clips, method="compose")

    print(f"\nRendering final video to: {OUTPUT_VIDEO}")
    print(f"Total duration: {final_video.duration:.1f} seconds (~{final_video.duration/60:.1f} minutes)")
    
    final_video.write_videofile(
        str(OUTPUT_VIDEO),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        bitrate="4000k",
        logger="bar"
    )

    print("\n" + "=" * 60)
    print(f"SUCCESS! Tutorial video generated at:\n{OUTPUT_VIDEO}")
    print(f"File size: {OUTPUT_VIDEO.stat().st_size / (1024*1024):.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
