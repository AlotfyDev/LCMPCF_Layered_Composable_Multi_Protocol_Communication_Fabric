#!/usr/bin/env python3
"""
Translate Arabic content in CSV files to English while preserving technical terms.
This script handles the specific patterns found in the roadmap CSV matrices.
"""
import csv
import re
import sys
from pathlib import Path

# Specific Arabic technical translations found in CSV content
ARABIC_TO_ENGLISH = {
    # Security related
    "BaseTransporter يرسل بايتات نصية بدون أي تشفير": "BaseTransporter sends plain bytes without any encryption",
    "جميع القنوات (TCP,UDS,IPC,WS,Subprocess) غير آمنة": "all channels (TCP,UDS,IPC,WS,Subprocess) are unencrypted",
    "التطبيقات التي تحتاج اتصالاً شبكيًا آمنًا": "Applications requiring secure network connections",
    "مكشوفة بالكامل": "fully exposed",
    "A2A عبر الإنترنت": "A2A over internet",
    "gRPC خارجي": "external gRPC",
    "Webhooks خارجية": "external webhooks",
    "يفتقر إلى": "lacks",
    "المشروع": "the project",
    "توثيق": "documentation",
    
    # Transport related
    "الـ Transporters": "Transporters",
    "يرسلون نصًا بدون تشفير": "send plain text without encryption",
    "الميزة مطلوبة لـ Gateway Mode": "feature required for Gateway Mode",
    "inter-container traffic": "inter-container traffic",
    "لا توجد آلية للحد من معدل الإرسال": "No mechanism to limit sending rate",
    "عند ازدحام المتلقي": "when receiver is congested",
    "قد ينفجر في الذاكرة": "may overflow in memory",
    "أثناء التحميل الثقيل": "during heavy load",
    "خاصًا مع التسلسل الهرمي": "especially with layered composition",
    "Composite -> multiple children": "Composite -> multiple children",
    
    # Common patterns
    "تم حل المشقة": "The issue is resolved",
    "لا يتطلب تغيير": "no changes required",
    "ولا يتطلب تغيير": "and no changes required",
    # Add more as discovered...
}

def has_arabic(text):
    """Check if text contains Arabic characters."""
    if not text:
        return False
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    return bool(arabic_pattern.search(text))

def translate_text(text):
    """Translate Arabic text to English, preserving technical terms."""
    if not text or not has_arabic(text):
        return text
    
    # Try specific translations first
    for arabic, english in ARABIC_TO_ENGLISH.items():
        if arabic in text:
            text = text.replace(arabic, english)
    
    return text

def process_csv_files():
    """Process all CSV files in the roadmap directory."""
    csv_dirs = [
        Path(".docs/roadmap_to_full_production_ready/missing_components"),
        Path(".docs/roadmap_to_full_production_ready/buggy_components"),
        Path(".docs/roadmap_to_full_production_ready/domain_gaps"),
    ]
    
    for csv_dir in csv_dirs:
        if not csv_dir.exists():
            continue
        for csv_file in sorted(csv_dir.glob("*.csv")):
            print(f"Processing {csv_file.relative_to(Path.cwd())}")
            
    return "Ready to process files"

if __name__ == "__main__":
    process_csv_files()