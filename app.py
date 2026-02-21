import streamlit as st
import google.generativeai as genai
import requests
from PIL import Image, ImageDraw, ImageFont
import json
import io
import os
import urllib.request

# ==========================================
# 1. 系統設定與快取函式 (Configuration & Cache)
# ==========================================
st.set_page_config(page_title="簡轉繁線索卡自動轉換器", layout="wide", page_icon="🎴")

FONT_OPTIONS = {
    "思源黑體 (Noto Sans TC)": "[https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf](https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf)",
    "思源宋體 (Noto Serif TC)": "[https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/TraditionalChinese/NotoSerifCJKtc-Regular.otf](https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/TraditionalChinese/NotoSerifCJKtc-Regular.otf)"
}

@st.cache_resource(show_spinner="正在下載/載入字體庫...")
def get_font_path(font_name: str, font_url: str) -> str:
    font_dir = "./fonts"
    if not os.path.exists(font_dir):
        os.makedirs(font_dir)
        
    ext = font_url.split(".")[-1]
    safe_name = font_name.split(" ")[0]
    font_path = os.path.join(font_dir, f"{safe_name}.{ext}")
    
    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(font_url, font_path)
        except Exception as e:
            st.error(f"字體下載失敗: {e}")
            return ""
    return font_path

# ==========================================
# 2. 核心 API 模組 (API Modules)
# ==========================================
def analyze_image_with_gemini(image: Image.Image, api_key: str, model_name: str) -> list:
    """呼叫 Gemini API 進行簡體辨識與座標提取"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name) 
    
    width, height = image.size
    prompt = f"""
    你是一個專業的繁體中文在地化與排版專家。
    請分析這張圖片（尺寸：寬 {width}px, 高 {height}px），找出所有「簡體中文」文字。
    將這些文字翻譯成「繁體中文」。
    請為每段文字估算它在圖片中的邊界框 (Bounding Box) 以及主要的文字顏色。

    必須回傳 JSON 陣列格式，格式如下：
    [
      {{
        "text": "繁體翻譯後的文字",
        "box": [ymin, xmin, ymax, xmax],
        "hex_color": "#FFFFFF"
      }}
    ]
    """
    
    # 修正重點：強制使用 JSON 模式，避免 Markdown 解析錯誤
    response = model.generate_content(
        [prompt, image],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json"
        )
    )
    
    try:
        data = json.loads(response.text)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini 回傳的格式非有效 JSON。原始回傳內容：\n{response.text}") from e

def remove_text_with_clipdrop(image_bytes: bytes, api_key: str) -> bytes:
    """呼叫 Clipdrop API 進行文字擦除"""
    # 修正重點：正確的 Clipdrop Text Remover API 網址
    url = "[https://clipdrop-api.co/text-remover/v1](https://clipdrop-api.co/text-remover/v1)"
    headers = {"x-api-key": api_key}
    files = {"image_file": ("image.png", image_bytes, "image/png")}
    
    response = requests.post(url, headers=headers, files=files)
    
    if response.status_code == 200:
        return response.content
    else:
        error_msg = response.json().get('error', response.text)
        raise Exception(f"Clipdrop API 錯誤 (狀態碼 {response.status_code}): {error_msg}")

# ==========================================
# 3. 圖像處理模組 (Image Processing)
# ==========================================
def draw_text_on_image(bg_image: Image.Image, text_data: list, font_path: str) -> Image.Image:
    result_img = bg_image.copy()
    draw = ImageDraw.Draw(result_img)
    
    for item in text_data:
        try:
            text = item.get("text", "")
            box = item.get("box", [0, 0, 0, 0])
            color = item.get("hex_color", "#FFFFFF")
            
            ymin, xmin, ymax, xmax = box
            box_w = xmax - xmin
            box_h = ymax - ymin
            
            if box_w <= 0 or box_h <= 0 or not text:
                continue
                
            font_size = box_h  
            font = ImageFont.truetype(font_path, int(font_size))
            
            lines = []
            while font_size > 8:
                font = ImageFont.truetype(font_path, int(font_size))
                lines = []
                current_line = ""
                
                for char in text:
                    test_line = current_line + char
                    bbox = font.getbbox(test_line)
                    w = bbox[2] - bbox[0]
                    if w <= box_w:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = char
                if current_line:
                    lines.append(current_line)
                    
                line_spacing = int(font_size * 0.2)
                total_h = sum([font.getbbox(l)[3] - font.getbbox(l)[1] for l in lines])
                total_h += line_spacing * (len(lines) - 1)
                
                if total_h <= box_h:
                    break
                    
                font_size -= 2 
                
            y_text = ymin
            for line in lines:
                bbox = font.getbbox(line)
                h = bbox[3] - bbox[1]
                draw.text((xmin, y_text), line, font=font, fill=color)
                y_text += h + int(font_size * 0.2)
                
        except Exception as e:
            st.warning(f"繪製文字區塊時發生錯誤，區塊內容: {item.get('text')}, 錯誤: {e}")
            
    return result_img

# ==========================================
# 4. 主程式 UI 流程 (Streamlit App Flow)
# ==========================================
def main():
    st.title("🎴 簡轉繁線索卡自動轉換器")
    st.markdown("結合 **Google Gemini** 與 **Clipdrop** 進行文字辨識、智慧擦除與無縫繁體合成。")
    
    if "step" not in st.session_state:
        st.session_state.step = 0
    if "original_image" not in st.session_state:
        st.session_state.original_image = None
    if "gemini_data" not in st.session_state:
        st.session_state.gemini_data = []
    if "bg_image_bytes" not in st.session_state:
        st.session_state.bg_image_bytes = None
        
    def reset_state():
        st.session_state.step = 0
        st.session_state.gemini_data = []
        st.session_state.bg_image_bytes = None

    st.sidebar.header("🔑 API 設定")
    gemini_key = st.sidebar.text_input("Gemini API Key", type="password")
    gemini_model = "gemini-1.5-pro"
    clipdrop_key = st.sidebar.text_input("Clipdrop API Key", type="password")
    
    st.sidebar.divider()
    st.sidebar.info("使用說明：\n1. 上傳原圖\n2. AI 辨識與校對文字座標\n3. 生成無字底圖\n4. 選擇字體並合成最終圖片")

    uploaded_file = st.file_uploader("上傳欲轉換的原始線索卡 (支援 JPG, PNG)", type=["jpg", "jpeg", "png"], on_change=reset_state)
    
    if not uploaded_file:
        st.info("請先上傳一張圖片以開始流程。")
        return

    image = Image.open(uploaded_file).convert("RGB")
    st.session_state.original_image = image
    
    with st.expander("預覽原始圖片", expanded=False):
        st.image(image, caption="原始上傳圖片", use_container_width=True)

    if not gemini_key or not clipdrop_key:
        st.warning("⚠️ 請先於左側邊欄填寫 Gemini 與 Clipdrop API Key。")
        return

    st.divider()

    st.header("步驟 1：AI 大腦辨識與人工校對")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔍 執行 AI 辨識", type="primary"):
            with st.spinner(f"Gemini ({gemini_model}) 正在解析文字與座標..."):
                try:
                    data = analyze_image_with_gemini(image, gemini_key, gemini_model)
                    st.session_state.gemini_data = data
                    st.session_state.step = 1
                    st.success("辨識完成！請在右側表格校對資料。")
                except Exception as e:
                    st.error(f"Gemini 辨識發生錯誤：\n{str(e)}")
                    st.info("💡 提示：如果看到 '404 models/xxx is not found'，請更換 Gemini 模型再試一次。")
                    
    with col2:
        if st.session_state.step >= 1:
            st.markdown("👇 **您可以在下方表格直接修改繁體文字、邊界框 (ymin, xmin, ymax, xmax) 或色碼：**")
            edited_data = st.data_editor(
                st.session_state.gemini_data, 
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "text": st.column_config.TextColumn("繁體翻譯", required=True),
                    "box": st.column_config.ListColumn("邊界框座標 [ymin, xmin, ymax, xmax]"),
                    "hex_color": st.column_config.TextColumn("HEX 顏色碼", required=True)
                }
            )
            
            if st.button("✅ 確認文字與座標無誤，進行下一步"):
                st.session_state.gemini_data = edited_data
                st.session_state.step = 2
                st.rerun()

    if st.session_state.step < 2:
        return
        
    st.divider()

    st.header("步驟 2：全自動背景修補與預覽")
    
    if st.button("🧹 呼叫 Clipdrop 清除底圖文字", type="primary"):
        with st.spinner("Clipdrop 正在進行背景修補... (這可能需要幾秒鐘)"):
            try:
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()
                
                bg_bytes = remove_text_with_clipdrop(image_bytes, clipdrop_key)
                st.session_state.bg_image_bytes = bg_bytes
                st.success("底圖修補成功！")
            except Exception as e:
                st.error(f"Clipdrop 修補發生錯誤：{str(e)}")

    if st.session_state.bg_image_bytes:
        bg_image = Image.open(io.BytesIO(st.session_state.bg_image_bytes)).convert("RGB")
        st.image(bg_image, caption="無字底圖預覽", use_container_width=True)
        
        if st.button("✅ 底圖修補完美，進行最後合成"):
            st.session_state.step = 3
            st.rerun()

    if st.session_state.step < 3:
        return

    st.divider()

    st.header("步驟 3：自選字體與精準合成")
    
    font_choice = st.selectbox("請選擇合成字體", list(FONT_OPTIONS.keys()))
    font_url = FONT_OPTIONS[font_choice]
    
    if st.button("🎨 生成最終圖片", type="primary"):
        with st.spinner("正在下載字體並合成最終圖片..."):
            font_path = get_font_path(font_choice, font_url)
            
            if font_path:
                bg_image = Image.open(io.BytesIO(st.session_state.bg_image_bytes)).convert("RGB")
                
                final_image = draw_text_on_image(
                    bg_image=bg_image, 
                    text_data=st.session_state.gemini_data, 
                    font_path=font_path
                )
                
                st.success("🎉 合成完成！")
                st.image(final_image, caption="最終線索卡", use_container_width=True)
                
                buf = io.BytesIO()
                final_image.save(buf, format="PNG")
                byte_im = buf.getvalue()
                
                st.download_button(
                    label="📥 下載最終圖片",
                    data=byte_im,
                    file_name="translated_clue_card.png",
                    mime="image/png",
                )

if __name__ == "__main__":
    main()
