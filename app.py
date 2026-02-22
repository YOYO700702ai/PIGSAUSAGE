import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw
import json
import pandas as pd

# --- 頁面設定 ---
st.set_page_config(page_title="步驟一：AI 文字辨識測試", layout="wide")
st.title("🕵️‍♂️ 線索卡轉換器 - 步驟 1 (含座標預覽)")
st.markdown("上傳圖片後，Gemini 會辨識文字、翻譯成繁體，並自動將 AI 比例座標轉換為真實像素畫在圖片上！")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("🔑 API 設定")
    gemini_api_key = st.text_input("請輸入 Gemini API Key", type="password")
    st.markdown("---")
    st.info("💡 提示：目前僅測試步驟 1，暫時不需要 Clipdrop 的金鑰。")

# --- 主畫面 ---
uploaded_file = st.file_uploader("上傳要測試的圖片 (支援 JPG, PNG)", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    # 讀取圖片並取得真實長寬
    original_image = Image.open(uploaded_file)
    img_width, img_height = original_image.size
    
    # 左右排版：左邊放原圖，右邊等一下放畫了紅框的預覽圖
    col1, col2 = st.columns(2)
    with col1:
        st.image(original_image, caption=f"原始圖片 ({img_width}x{img_height} px)", use_container_width=True)

    if st.button("🚀 開始 AI 辨識、翻譯與標註", type="primary"):
        if not gemini_api_key:
            st.warning("請先在左側欄輸入 Gemini API Key！")
        else:
            with st.spinner("🧠 Gemini 正在看圖並計算座標中，請稍候..."):
                try:
                    # 1. 設定 API
                    genai.configure(api_key=gemini_api_key)
                    model = genai.GenerativeModel(
                        model_name="gemini-2.5-pro",
                        generation_config={"response_mime_type": "application/json"}
                    )

                    # 2. 撰寫 Prompt
                    prompt = """
                    請辨識這張圖片中的所有「簡體中文」文字，並將其翻譯為「繁體中文」。
                    請以「完整的句子或段落」為單位。
                    
                    請嚴格按照以下 JSON Array 格式輸出：
                    [
                      {
                        "original_text": "原始簡體字",
                        "translated_text": "繁體翻譯",
                        "box_normalized": [ymin, xmin, ymax, xmax], 
                        "hex_color": "#000000",
                        "font_style": "sans-serif"
                      }
                    ]
                    注意：box_normalized 的數值必須是 0 到 1000 之間的整數，代表千分比座標。
                    """

                    # 3. 呼叫 API
                    response = model.generate_content([original_image, prompt])
                    result_data = json.loads(response.text)

                    # 4. 建立一份圖片複本用來畫紅框
                    annotated_image = original_image.copy()
                    draw = ImageDraw.Draw(annotated_image)

                    # 5. 處理資料：座標轉換與繪製
                    processed_data = []
                    for item in result_data:
                        # 取得 0-1000 的標準化座標
                        ymin_norm, xmin_norm, ymax_norm, xmax_norm = item["box_normalized"]
                        
                        # 轉換為真實像素 (Absolute Pixels)
                        abs_ymin = int((ymin_norm / 1000) * img_height)
                        abs_xmin = int((xmin_norm / 1000) * img_width)
                        abs_ymax = int((ymax_norm / 1000) * img_height)
                        abs_xmax = int((xmax_norm / 1000) * img_width)
                        
                        # PIL 畫矩形需要的格式是 [x0, y0, x1, y1] (即 [左, 上, 右, 下])
                        box_absolute = [abs_xmin, abs_ymin, abs_xmax, abs_ymax]
                        
                        # 在圖片上畫紅色矩形框 (線條寬度設為 3)
                        draw.rectangle(box_absolute, outline="red", width=3)
                        
                        # 將處理好的資料整理成要顯示在表格的格式
                        processed_data.append({
                            "原文 (參考)": item.get("original_text", ""),
                            "繁體翻譯 (可修改)": item.get("translated_text", ""),
                            "真實座標 [左,上,右,下]": box_absolute,
                            "顏色 HEX": item.get("hex_color", "#000000"),
                            "字體風格": item.get("font_style", "sans-serif")
                        })

                    # 6. 在右側顯示畫好紅框的圖片
                    with col2:
                        st.image(annotated_image, caption="AI 座標辨識結果預覽", use_container_width=True)

                    st.success("✅ 辨識完成！請比對上方右圖的紅框，並在下方表格確認或修改文字與座標。")
                    
                    # 7. 顯示資料表格供使用者修改
                    df = pd.DataFrame(processed_data)
                    edited_df = st.data_editor(
                        df,
                        num_rows="dynamic",
                        use_container_width=True
                    )
                    
                    # 儲存到 session_state
                    st.session_state['step1_data'] = edited_df.to_dict('records')

                except Exception as e:
                    st.error(f"❌ 處理過程中發生錯誤：{str(e)}")
                    st.markdown("請檢查 API Key 是否正確，或是 JSON 解析是否失敗。")

# --- 確認按鈕區塊 ---
if 'step1_data' in st.session_state:
    st.markdown("---")
    st.markdown("### 步驟 1 驗證區")
    st.info("💡 提示：在真實應用中，使用者可以在上面的表格微調『真實座標 [左,上,右,下]』的像素值，確保最後合成不會印到框外。")
    if st.button("✅ 確認文字與座標無誤，進入步驟 2 (去除文字背景)"):
        st.balloons()
        st.success("資料已備妥！我們已經成功取得了繁體中文、真實像素座標和顏色。")
        # 這裡未來會接續步驟 2 的 Clipdrop 程式碼
