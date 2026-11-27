# NeonClipping

**Dán một liên kết. Nhận clip 9:16 có phụ đề trong khoảng hai phút. Miễn phí, chạy cục bộ, mã nguồn mở.**

NeonClipping biến các video dài trên YouTube / Twitch / Kick (hoặc file MP4 của chính bạn) thành clip dọc có phụ đề, kèm tiêu đề và câu hook cho từng clip. Mọi thứ chạy trên máy của bạn: không tài khoản, không đăng ký thuê bao, không tải lên.

[![Star on GitHub](https://img.shields.io/github/stars/iamajmeena/neonclipping?style=for-the-badge&logo=github&label=Star%20on%20GitHub)](https://github.com/iamajmeena/neonclipping) [![Instagram](https://img.shields.io/badge/Follow-%40iamajmeena-E4405F?style=for-the-badge&logo=instagram&logoColor=white)](https://www.instagram.com/iamajmeena/)

🌐 **Trang web với cài đặt Windows một cú nhấp:** <https://iamajmeena.github.io/neonclipping/>

**Tác giả: [Ajay K Meena](https://www.instagram.com/iamajmeena/)** (Đạo diễn, DOP, chuyên gia chỉnh màu, giảng viên DaVinci Resolve, Jaipur). Nếu NeonClipping giúp bạn tiết kiệm thời gian, hãy ⭐ star repo và theo dõi [@iamajmeena](https://www.instagram.com/iamajmeena/) trên Instagram.

**Cắt một stream 85 phút trong 97 giây, 100% cục bộ, chi phí API bằng không.** (đã đo thực tế, xem [Cách nó tìm ra những khoảnh khắc hay](#cách-nó-tìm-ra-những-khoảnh-khắc-hay))

### So sánh NeonClipping với các công cụ cắt clip khác

| | **NeonClipping** | OpusClip (đám mây) | Các công cụ tự host bằng Docker (SupoClip, OpenShorts, Reelsaw) |
|---|---|---|---|
| Chạy ở đâu | PC của bạn, không tải lên gì cả | Máy chủ của họ | Máy của bạn hoặc máy chủ của bạn |
| Chi phí | Miễn phí, không tài khoản, không credit | Thuê bao / credit | Miễn phí (một số cần API key của LLM hoặc cài Docker) |
| Cài đặt | Một file `.bat` trên Windows, `install.sh` trên Mac/Linux, không Docker | Không cần (web) | Docker |
| Liên kết YouTube + Twitch + Kick | Có | Có | Chủ yếu YouTube |
| Stream rất dài | Ưu tiên âm thanh (79 MB cho 85 phút); video 24 giờ: chọn đoạn cần lấy, không bao giờ tải toàn bộ | Bị giới hạn dung lượng tải lên | Thường bị giới hạn bởi độ dài hoặc ổ đĩa |
| Bố cục game (facecam + gameplay) | 11 bố cục, tự động tìm facecam | Hạn chế | Tùy công cụ |
| Cắt clip khi đang livestream | Có, dựa trên đột biến chat, điều khiển từ xa bằng điện thoại | Không | Hiếm |
| Chất lượng tải xuống | Mặc định 1080p, tùy chọn 4K ngay cạnh nút Get preview | không áp dụng | Tùy công cụ |
| Phụ đề | 5 phong cách, 52 ngôn ngữ, Hinglish, bật/tắt, nhận biết đoạn yên lặng | Mẫu có sẵn | Tùy công cụ |

![demo](docs/demo.gif)

![UI](docs/neonclipping-ui.jpg)

📘 **Hướng dẫn (tiếng Hindi + tiếng Anh, PDF):** [English](docs/NeonClipping-Guide-English.pdf) · [हिंदी](docs/NeonClipping-Guide-Hindi.pdf)  
🤖 **Để một AI agent cài đặt giúp bạn:** sao chép [docs/NEONCLIPPING-AGENT-SETUP-PROMPT.txt](docs/NEONCLIPPING-AGENT-SETUP-PROMPT.txt) vào Claude Code, Codex CLI hoặc Cursor.

## Cách nó tìm ra những khoảnh khắc hay

Hai chế độ, một nút bấm.

**⚡ Chế độ Fast (mặc định, cho video trên 10 phút)** học theo chiêu làm nên tốc độ của các công cụ cắt clip nhanh nhất: không bao giờ xem toàn bộ video.

1. Chỉ tải **âm thanh** (79 MB cho một video 85 phút, khoảng 10 giây).
2. Lấy bản chép lời miễn phí từ phụ đề của chính YouTube (có thời gian theo từng từ). Không cần mô hình giọng nói. Với các nguồn khác, mô hình Whisper chạy cục bộ được dùng làm phương án dự phòng.
3. Chấm điểm toàn bộ bản âm thanh theo *những cú nhảy âm lượng đột ngột* (so với đường nền cục bộ 2 phút), *giọng nói cao lên* (năng lượng ở dải 2–4 kHz) và chuyển tiếp từ yên lặng sang ồn ào.
4. Lấy những khoảnh khắc tốt nhất, cho một LLM cục bộ (Ollama) đọc bản chép lời của từng khoảnh khắc rồi chấm điểm, viết tiêu đề và câu hook. Điểm bắt đầu và kết thúc được bám vào ranh giới câu trong giới hạn độ dài Min/Max của bạn.
5. Chỉ tải **đúng những đoạn đã chọn** của video (không tải cả file), cắt chính xác bằng cách khớp âm thanh của chúng với bản âm thanh, và dựng clip 1080x1920 với phụ đề được ghi cứng vào hình.

**🔬 Chế độ Deep** tải toàn bộ video, bổ sung chuyển động optical-flow (OpenCV Farneback: vật thể nhanh, va chạm, lia máy) và mật độ cắt cảnh vào các tín hiệu âm thanh, chọn ra danh sách rút gọn nhiều gấp 4 lần và cho LLM 15 giây ngữ cảnh trước và sau mỗi khoảnh khắc.

Đo trên một máy (RTX 2060, 16 luồng), chế độ Fast, mỗi nguồn 3 clip:

| Nguồn | Thời gian |
|---|---|
| Stream YouTube 85 phút (phụ đề YouTube) | **97 giây** |
| VOD Twitch 3 giờ (không phụ đề, mô hình giọng nói cục bộ) | **136 giây** |
| Trailer YouTube 90 giây | 21 giây |
| MP4 cục bộ 90 giây | 14 giây |

Số liệu của bạn phụ thuộc vào mạng và CPU.

## Cách nó quyết định đâu là khoảnh khắc hay

Mỗi khoảnh khắc ứng viên được chấm điểm từ nhiều tín hiệu, rồi những khoảnh khắc tốt nhất được giữ lại:

| Tín hiệu | Nó tìm kiếm điều gì |
|---|---|
| Nhảy âm lượng | Một tiếng nổ hoặc tiếng hét đột ngột so với hai phút trước đó |
| Giọng cao lên | Năng lượng trong dải 2–4 kHz (gào thét, la hét) |
| Nội dung lời nói | "oh my god", "oh shit", "run", "police", "bhaago", "arre yaar" và tương tự (tiếng Anh, Hinglish, Hindi) |
| Hành động trên màn hình | Chuyển động nhanh (optical flow), chớp sáng giống vụ nổ, nhấp nháy đèn đỏ/xanh, cắt cảnh |
| Điểm AI | Một LLM cục bộ nhỏ đọc bản chép lời: cảm xúc, câu chốt, điểm bùng nổ |

**Nó học từ bạn.** Các khoảnh khắc được tạo ra có điều khiển năm sao trong phần kết quả và My clips. Đánh giá ở lại trên máy của bạn (`data/feedback.jsonl`). Sau ít nhất tám **khoảnh khắc khác nhau**, với sự pha trộn hữu ích giữa các đánh giá mạnh/yếu và các số đo khác nhau, trọng số xếp hạng cục bộ có thể thích nghi. Nhấp lặp lại sẽ cập nhật đánh giá mới nhất của khoảnh khắc đó; các bản đã chỉnh sửa lại giữ chung một danh tính huấn luyện. Toàn bộ lịch sử đánh giá được giữ nguyên. Việc này huấn luyện một bộ xếp hạng sở thích nhỏ, không phải mô hình nền tảng. Không có gì được tải lên.

## Tính năng

- **Make clips** một cú nhấp, tiến trình trực tiếp, các clip xuất hiện lần lượt kèm bản xem trước và nút tải MP4.
- **Độ dài clip Min / Max** (ví dụ 30–80 giây). Clip kết thúc tại ranh giới câu.
- **Vị trí facecam đặt sẵn** (trên-trái, trên-phải, dưới-trái, dưới-phải, dưới-giữa, không có) cho các bố cục streamer thường gặp, được ghi nhớ giữa các phiên. Hoặc tự vẽ khung mặt và khung gameplay trong trình chỉnh sửa.
- **11 bố cục gốc:** camera trên/dưới gameplay, nền mờ lấp đầy, cắt toàn màn hình, chỉ gameplay, bốn lớp phủ ở góc, facecam hình tròn và chia đôi màn hình. Chọn mặt/game độc lập và thanh trượt kích thước khuôn mặt. Vùng an toàn của nền tảng chỉ hiển thị khi xem trước.
- Phong cách phụ đề: GTA Neon, Impact, Clean, Hormozi và MrBeast. Canh thời gian theo từng từ, sửa được từng từ, xuất SRT.
- **Tiêu đề mở đầu:** mặc định tám giây, chỉnh được từ 2–60 giây, có nền đen cho các bố cục gameplay sáng và facecam. Dùng **Improve opening heading** để viết một câu hỏi khơi gợi tò mò bám sát nội dung từ bản chép lời đã chọn. Các clip hiện có có thể áp dụng diện mạo mới mà không cần tải lại hay tìm lại khoảnh khắc.
- **Pha trộn khoảnh khắc (Moment mix):** Balanced kết hợp các đề xuất theo hoạt động và theo bản chép lời; Action ưu tiên năng lượng; Dialogue ưu tiên câu chuyện, hài hước và những điểm sâu sắc. Lựa chọn cuối cùng giảm các khoảnh khắc chồng lấn và lặp lại. Balanced/Dialogue ưu tiên bộ chấm điểm cục bộ Gemma 4 nếu đã được cài sẵn; các mô hình cục bộ khác vẫn là phương án dự phòng. Việc này thay đổi quy tắc tuyển chọn và prompt, không thay đổi trọng số của mô hình nền tảng.
- **Phụ đề tùy chỉnh:** họ phông chữ đã cài, kích thước, màu chữ/màu từ đang phát/màu viền, số từ mỗi phụ đề và các hồ sơ lưu cục bộ. Nhập SRT/ASS/WebVTT hoặc dán văn bản phụ đề, chỉnh thời gian từng từ, tách/gộp và dịch chuyển phụ đề. Thời gian theo từ bên trong một cue từ file nhập vào là ước tính. Tải WebVTT cùng với SRT.
- **Trình khám phá bản chép lời:** chủ động tạo hoặc nhập bản chép lời của toàn bộ nguồn, tìm cụm từ trong các cue, duyệt theo trang, và nhấp vào từ đầu/từ cuối để xuất đoạn đó. Bản chép lời đã lưu trong bộ nhớ đệm được Make clips tái sử dụng và bị vô hiệu hóa khi nguồn thay đổi.
- **Cắt lại clip đã lưu:** trong *Edit saved clips*, thay đổi Start / End rồi nhấn *Only this clip*; clip được cắt lại từ video đã lưu và phụ đề di chuyển theo vết cắt (3 đến 180 giây, trong phạm vi video đã lưu).
- **52 ngôn ngữ phụ đề** trong menu Language, xem phần Giới hạn thật lòng để biết các lưu ý.
- **Đánh giá hình ảnh tùy chọn:** một mô hình hình ảnh Gemma4 tương thích đã cài sẵn mô tả ba khung hình thực tế của cảnh. Xem lại chúng trong trình chỉnh sửa hoặc bật đánh giá hình ảnh để tự động tinh chỉnh ứng viên. Tính năng này tắt theo mặc định và có thể làm tăng thời gian suy luận trên CPU. Mô tả hình ảnh lấy mẫu có thể không chắc chắn và không xác minh được một sự kiện hoàn chỉnh trong game. Bằng chứng đã lưu được tái sử dụng khi chỉnh sửa lại.
- **Phụ đề Hinglish**: lời nói tiếng Hindi được viết bằng chữ cái tiếng Anh ("kya haal hai bhai") theo mặc định. Hãy chọn rõ Hinglish / हिंदी / English nếu bạn muốn. Chế độ Fast dùng phụ đề nguồn có sẵn; Best Hindi dùng rõ ràng nhận dạng large-v3 cục bộ và có thể chậm hơn trên GPU nhỏ. Thiếu phụ đề nguồn thì cần nhận dạng cục bộ.
- **Make clips dùng chính thiết lập của bạn**: vị trí facecam đặt sẵn hoặc các khung bạn vẽ ở bước 03.
- Xếp hạng điểm nhấn bằng chuyển động optical-flow + âm thanh, xuất NVENC chính xác theo khung hình (dự phòng bằng x264).
- Việc xử lý và thư viện clip đều cục bộ. Nhập trực tuyến, AI tùy chọn, tìm kiếm stock và đăng bài chủ động sẽ liên hệ với các dịch vụ tương ứng mà bạn chọn. Máy chủ desktop mặc định chỉ gắn với `127.0.0.1`.

## Sửa clip sau khi đã tạo

![Trình chỉnh sửa clip đã lưu với mười một bố cục](docs/saved-clip-editor.jpg)

Mở **My clips → Edit clip**. Trình chỉnh sửa đã lưu gồm cả **11 bố cục vị trí/hình dạng loa**, thanh trượt kích thước loa, từ phụ đề sửa được, phong cách phụ đề và chiều cao phụ đề.

- **Apply to this clip** cập nhật clip đang mở.
- **Apply to this video's clips** cập nhật các clip đã lưu hiện tại gắn với cùng một URL nguồn. Mỗi clip giữ nguyên dấu thời gian, bản chép lời, tiêu đề và hook của nó. Các clip mới đang được tạo không nằm trong ảnh chụp này.
- Việc tải nguồn, khám phá điểm nhấn và nhận dạng giọng nói **không bị lặp lại**. Phụ đề ghi cứng và khung hình đòi hỏi mã hóa một file MP4 cuối mới.
- File nguồn gốc phải còn trong `data/`. Các MP4 trước đó được giữ lại; thư viện hiển thị phiên bản mới nhất. Các bản xuất cũ thiếu thời gian từng từ đã lưu có thể khôi phục phụ đề từ file SRT của chúng, với thời gian từng từ gần đúng.
- Thao tác này chỉnh sửa các khoảnh khắc đã chọn; muốn thay đổi điểm bắt đầu/kết thúc của clip hoặc ngôn ngữ nói thì cần một quy trình cắt/chép lời riêng.

Kiểm chứng trên một nguồn dài 796,9 giây: cả 11 bố cục và năm phong cách phụ đề đều xuất ra kèm âm thanh và giải mã thành công. Một lần cập nhật bố cục/phong cách cho bảy clip mất 119,58 giây trong khi tái sử dụng chính xác nguồn, khoảng và danh sách từ của từng clip. Đây là kiểm tra cục bộ, không phải thời gian chạy đảm bảo hay thước đo chất lượng phụ đề.

Chạy bộ kiểm thử hồi quy di động bằng `python -m unittest discover -s tests -v`.

## Cài đặt

**Dễ nhất (Windows):** tải [`NeonClipping-Setup.bat`](https://github.com/iamajmeena/neonclipping/releases/latest/download/NeonClipping-Setup.bat) từ [trang web](https://iamajmeena.github.io/neonclipping/) hoặc trang Releases rồi nhấp đúp vào nó. Nó kiểm tra PC của bạn, cài Python và FFmpeg nếu thiếu, cài NeonClipping vào `%LOCALAPPDATA%\NeonClipping`, tạo lối tắt trên Desktop và mở ứng dụng. Mac/Linux: `install.sh` (mới, chưa được thử trên máy Mac thật). Hoặc làm theo các bước dưới đây.

Yêu cầu: Python 3.10 đến 3.13 (Python mới nhất thường chưa có wheel cho các gói giọng nói/thị giác; trình cài đặt Mac/Linux sẽ chọn cho bạn một phiên bản được hỗ trợ), FFmpeg có trong PATH. Tùy chọn nhưng khuyến nghị: [Ollama](https://ollama.com) với `ollama pull llama3.2:3b` cho tiêu đề, hook và điểm số bằng AI (không có nó, clip được chọn bằng điểm âm thanh/chuyển động), và GPU NVIDIA cho NVENC và faster-whisper.

```bash
git clone https://github.com/iamajmeena/neonclipping
cd neonclipping
# Windows
./run.ps1
# Linux / macOS
./run.sh
```

Mở <http://127.0.0.1:8770>, dán một liên kết, nhấn **⚡ Make clips**.

Hỗ trợ mô hình giọng nói bằng GPU tùy chọn (chỉ dùng khi video không có phụ đề YouTube):

```bash
.venv/bin/pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
```

Đặt `NEONCLIPPING_CPU=1` để ép dùng CPU. Đặt `NEONCLIPPING_PORT=9000` để dùng cổng khác.

**Mac / Linux / không có GPU NVIDIA:** bộ mã hóa video được chọn theo những gì chạy được trên máy của bạn: NVIDIA NVENC, rồi Apple VideoToolbox, rồi bộ mã hóa CPU (x264). Ép chọn một bộ bằng `NEONCLIPPING_ENCODER=nvenc|videotoolbox|x264`. Mô hình giọng nói bỏ qua lần thử GPU khi không có GPU CUDA và chạy trên CPU. `install.sh` và các kiểm thử đơn vị tự động chạy trên máy macOS, Ubuntu và Windows cho mọi thay đổi (xem tab *Actions*); người bảo trì chưa thử trình cài đặt Mac trên máy Mac của chính mình, nên hãy cho chúng tôi biết nếu nó trục trặc (Report a problem).

**Cài đặt (biến môi trường):** `NEONCLIPPING_LIVE_AUTO_HOURS` (mặc định 3) và `NEONCLIPPING_MIN_FREE_GB` (mặc định 8) điều khiển các phiên live theo dõi creator không người trông; một phiên cắt clip Live thủ công không có giới hạn thời gian và không có chốt chặn ổ đĩa.

## Cấu trúc mã nguồn

| File | Công việc |
|---|---|
| `app.py` | Máy chủ FastAPI, pipeline `/make`, xuất bản, thư viện |
| `smart.py` | Chấm điểm khoảnh khắc: bản chép lời + LLM cục bộ, bám ranh giới câu |
| `highlights.py` | Xếp hạng theo nhảy âm thanh / tiếng hét / optical-flow / cắt cảnh, giải mã song song |
| `captions_yt.py` | Bộ phân tích phụ đề YouTube theo thời gian từng từ (json3) |
| `captions.py` | Whisper cục bộ (ưu tiên GPU, dự phòng CPU), phong cách ASS/SRT |
| `translit.py` | Devanagari → Hinglish (từng từ, giữ nguyên thời gian) |
| `standalone.py`, `previews.py` | Nhập liên kết, khung hình xem trước sớm |

## Cắt clip trực tiếp (khi stream đang phát)

Dán liên kết kênh Twitch hoặc liên kết YouTube Live vào bảng **Live clipping** rồi nhấn Start. NeonClipping ghi lại stream (Streamlink), đọc chat ẩn danh, đếm tin nhắn theo các khoảng 10 giây và cắt một clip quanh mỗi đột biến chat (tốc độ chat hơn 2,5 sigma và gấp 2,5 lần đường nền 5 phút). Clip bắt đầu khoảng 24 giây *trước* đột biến, vì chat phản ứng sau khoảnh khắc diễn ra. Sau đó nó nhận phụ đề, một hook và tiêu đề, bố cục và khung facecam của bạn, cùng điểm viral như mọi clip khác. **Clip the last 30 s now** cắt theo yêu cầu, **Stop** kết thúc phiên. Nó chỉ hoạt động khi stream đang live; với video đã kết thúc hãy dùng Make clips.

Ngoài ra còn có phiên bản dòng lệnh trong `live/live_clip.py`.

## Creators (tự động cắt clip của streamer)

Thêm tên Twitch hoặc liên kết kênh Twitch / YouTube trong bảng **Creators**. NeonClipping kiểm tra mỗi phút; khi creator đó lên sóng, nó ghi lại stream và cắt các đột biến chat, dùng bố cục, khung facecam và phong cách phụ đề bạn đã chọn lúc thêm họ ("Use my current layout" cập nhật nó). Clip xuất hiện dưới tên creator và trong My clips.

- Mỗi lần một stream (ghi và dựng rất nặng); các creator khác chờ đến lượt.
- NeonClipping phải luôn mở. Các bản ghi không người trông dừng sau 3 giờ (một bản mới bắt đầu nếu creator vẫn đang live), dừng khi ổ đĩa còn trống dưới 8 GB, và file ghi lớn bị xóa sau khi clip cuối cùng được cắt.
- Nhấn **Stop** tạm dừng creator đó trong 30 phút; tắt rồi bật lại Auto sẽ tiếp tục ngay.
- Đã kiểm thử trên Twitch (ghi, đột biến chat, clip, feed). Kênh YouTube được phát hiện qua yt-dlp; một stream YouTube được cắt tự động chưa được chạy từ đầu đến cuối.

## Kiểm thử

`tests/` chứa một bộ kiểm thử đầu cuối chạy với máy chủ đang hoạt động: kiểm tra trang và API, mọi bố cục và phong cách phụ đề được dựng và đo, chỉnh sửa một / tất cả clip của một video, Make clips trên các nguồn YouTube / Twitch / cục bộ thật ở mọi chế độ và ngôn ngữ, cắt clip trực tiếp trên một stream thật, danh sách creator, đánh giá sao, trình cài đặt và trang web. Kiểm thử đơn vị bao quát quy tắc đột biến chat, nhóm phụ đề và chỉnh sửa lại. Lần chạy đầy đủ gần nhất nằm trong [`tests/REPORT.md`](tests/REPORT.md): 187 kiểm tra, tất cả đều đạt, cộng với 12 vấn đề mà lần chạy đó tìm thấy và đã sửa.

```
python -m unittest tests.test_captions tests.test_live tests.test_reedit
python tests/e2e.py static export edit creators feedback   # server must be running
python tests/e2e_make.py          # real downloads + transcription (about 25 min)
python tests/e2e_live.py          # needs a Twitch channel that is live
python tests/e2e_site.py          # website, links, release assets
python tests/make_report.py       # rebuild tests/REPORT.md
```

## Điều khiển cắt clip trực tiếp và điều khiển từ xa bằng điện thoại

Lấy cảm hứng từ một công cụ cắt clip live trên di động được giới thiệu trong reel của một creator (ứng dụng đó chưa phát hành nên không thể nghiên cứu gì về nó; chỉ những gì video cho thấy được sử dụng).

- **Đồng hồ đo độ hot của chat** khi stream đang live: 0-100%, từ các bình luận trong ~30 giây gần nhất so với tốc độ thường lệ của chính stream đó (đỉnh = gấp 4 lần thường lệ; những giây đầu dùng thang tuyệt đối), với nhãn *quiet / building momentum / hot / peak viral hype*.
- **Độ dài clip đặt sẵn** 10 giây / 20 giây / 30 giây / Auto: clip bắt đầu vài giây trước đỉnh chat; "Clip now" cắt cùng độ dài đó từ bản ghi live.
- **Văn bản hook** cho clip live từ AI, **tiêu đề stream** (đã loại bỏ emoji) hoặc văn bản của riêng bạn; **công tắc phụ đề** (tắt = clip nhanh hơn).
- Clip live giờ cũng có các tùy chọn phong cách (mẫu, logo, dòng credit, outro, nhạc, hoạt ảnh phụ đề).
- **Điều khiển từ xa bằng điện thoại:** khởi động NeonClipping bằng lối tắt *NeonClipping (phone access)* (`Start-NeonClipping-Phone.bat`, hoặc đặt `NEONCLIPPING_LAN=1`). Trong mục Live clipping, nó hiển thị một địa chỉ Wi-Fi và một mã PIN 6 chữ số. Trên điện thoại cùng Wi-Fi, mở địa chỉ đó (`/m`), nhập PIN, dán liên kết YouTube Live hoặc Twitch, chọn độ dài, xem đồng hồ đo độ hot, nhấn **Clip now**, rồi phát / lưu / chia sẻ các clip. Trên Android Chrome dùng "Add to Home screen" để có biểu tượng ứng dụng. PC làm mọi việc; điện thoại chỉ là điều khiển từ xa.
- **An toàn:** truy cập bằng điện thoại tắt trừ khi bạn khởi động theo cách đó (khi ấy máy chủ vẫn chỉ lắng nghe trên 127.0.0.1). Mọi thứ không phải PC đều cần PIN (sau 5 lần nhập sai, một địa chỉ bị khóa 10 phút; "New PIN" đăng xuất mọi điện thoại). Ngay cả khi có PIN, điện thoại cũng chỉ dùng được các tuyến live, library, make, clips, feedback và creators: tải lên, công cụ file, hàng đợi và chính mã PIN vẫn chỉ dành cho PC. Windows sẽ hỏi một lần có cho phép NeonClipping trên mạng riêng hay không: chọn Allow chỉ cho Wi-Fi ở nhà.
- Không bao gồm: ứng dụng Android gốc (trang điện thoại là một trang web hoạt động như ứng dụng), cắt clip live chạy trên chính điện thoại.

## Phụ đề: luôn dùng phụ đề của chính YouTube

Với liên kết YouTube, mọi clip đều dùng phụ đề theo thời gian từng từ của chính YouTube, ở mọi ngôn ngữ. Tiếng Hindi đến dưới dạng Devanagari và được chuyển thành Hinglish (gồm cả chữ nukta: kapde, padega, thoda); các vòng lặp từ bị cắt bỏ. Nó nhanh hơn mô hình giọng nói cục bộ và, trên âm thanh game, rõ ràng chính xác hơn: trên một stream tiếng Hindi 2 giờ, một lần chạy Make mất 197 giây với những câu đúng như "poori mod di yaar, kya bhai? arre pulis". Mô hình cục bộ "Accurate (turbo)" đã bị loại bỏ vì phụ đề của nó tệ hơn. Mô hình cục bộ duy nhất còn lại có chủ đích là **Best Hindi (large-v3, slow)**. Video không có phụ đề YouTube (file cục bộ, VOD Twitch) vẫn cần một mô hình cục bộ làm lựa chọn duy nhất; hãy kỳ vọng phụ đề thô hơn ở đó, hoặc nhập một file .srt.

## Phong cách & tính năng thêm

- **Mẫu (Templates):** bọc clip trong một *bài đăng X* (sáng hoặc tối), hộp *TikTok hook* hoặc khung phát sóng *Breaking news*. Gõ tên, handle và hook; thẻ, chữ cái avatar, dấu tích và dòng chạy chữ được vẽ cho bạn.
- **Thẻ nền:** thẻ video có đệm, bo góc trên một bản sao bị làm mờ, một màu, một dải chuyển màu hoặc hình ảnh của riêng bạn (làm tối, làm mờ).
- **Logo / watermark** (4 góc, kích thước, độ mờ), **dòng credit** (hoặc "Clip: tên kênh" tự động), **dải outro** trượt vào trong những giây cuối.
- **Nền nhạc:** một bản nhạc dưới giọng nói, dâng lên âm lượng đỉnh trong những giây cuối (âm lượng, đỉnh và độ dài đoạn dâng do bạn chọn).
- **Sáu hoạt ảnh phụ đề:** highlight (từng từ), pop-in, pop-in theo dòng, one by one, build up, full line.
- **Nhập phụ đề:** thả một file `.srt` hoặc `.ass`; các từ được canh thời gian theo clip và sửa được.
- Tất cả hoạt động trong Make clips, xuất đơn lẻ và "Edit saved clips" (kể cả "apply to all clips of this video").

## Tìm facecam của tôi

Chip **Find my facecam** (hoặc "tự động tìm khi tôi nhấn Make clips") xem 14 khung hình của video, tìm các hình chữ nhật có viền đứng yên cùng một chỗ, và giữ lại cái chứa khuôn mặt (mô hình khuôn mặt YuNet cục bộ nhỏ, giấy phép MIT, `models/`). Nó loại bỏ minimap của game và các bảng HUD, tìm webcam ở một góc hoặc nổi trên một cạnh, và trả lời "no facecam" khi không chắc chắn. Đo trên 30 stream đã lưu thật: tìm thấy webcam trên mọi stream có webcam; "not found" sạch sẽ trên trailer và video nói chuyện trực diện. Chưa hoàn hảo: một số khung chỉ bao phần mặt bên trong một webcam có viền.

## Stream dài với chatbot miễn phí

**AI parts** (bên dưới bước 01): dán một liên kết YouTube, NeonClipping chia phụ đề của video thành các phần ~25 phút và đưa ra một prompt sẵn sàng sao chép cho từng phần. Dán từng phần vào bất kỳ chatbot miễn phí nào, dán tất cả câu trả lời trở lại (JSON hoặc các dòng như `12:30-13:10 title`), đánh dấu các khoảnh khắc và nhấn Make clips: chỉ những đoạn đó được tải xuống và dựng. Một chatbot được đưa cho bản chép lời 9 giờ trong một lần chỉ đọc phần đầu; các phần nhỏ khắc phục điều đó. NeonClipping không gửi bất cứ thứ gì đi đâu cả; bước chatbot là thủ công.

## Báo cáo sự cố (tiếng Anh + tiếng Hindi)

Nút **Report a problem · समस्या बताएँ** (góc dưới-phải) giải thích, bằng tiếng Anh và tiếng Hindi, ba cách để cho người bảo trì biết điều gì đã hỏng. Bạn chọn mức độ chia sẻ và **không có gì được gửi đi trừ khi bạn nhấn nút**:

| Tùy chọn | Điều gì xảy ra | Ai nhìn thấy |
|---|---|---|
| **1 · GitHub issue (an toàn nhất)** | Mở một issue đã điền sẵn; bạn tự đọc và nhấn Submit | Công khai trên GitHub |
| **2 · Download diagnostics** | Lưu một file văn bản; bạn tự gửi nó (GitHub, Instagram DM, WhatsApp) | Chỉ người bạn gửi tới |
| **3 · Send directly (tùy chọn)** | Sau khi bạn đánh dấu vào ô cạnh đúng văn bản được hiển thị, gửi nó tới bộ thu thập của người bảo trì | Chỉ người bảo trì |

Nội dung văn bản gồm: phiên bản công cụ (ứng dụng, Python, Windows, ffmpeg, yt-dlp), các thông báo lỗi gần đây với nhãn ngắn như `youtube-bot-check`, và ghi chú của bạn nếu bạn viết. Liên kết video (chỉ giữ lại tên trang), tên người dùng trong đường dẫn, e-mail, địa chỉ IP và các giá trị giống token bị loại bỏ trước khi bất cứ thứ gì được hiển thị, ghi log hoặc chia sẻ. Không bao giờ đọc video, bản chép lời, cookie hay dữ liệu trình duyệt. Các tác vụ thất bại cũng được ghi vào `data/errors.log` trên chính máy của bạn (đã che thông tin nhạy cảm, tự động cắt ngắn); file đó không bao giờ rời khỏi máy trừ khi bạn chia sẻ nó.

Tùy chọn 3 ở trạng thái tắt ("not set up") cho đến khi một URL bộ thu thập được cấu hình; xem [`tools/report-worker`](tools/report-worker/README.md). Mã nguồn: [`report.py`](report.py), [`report.js`](report.js). Biểu mẫu issue: `.github/ISSUE_TEMPLATE/problem.yml`.

## Chất lượng nguồn (mặc định 1080p, tùy chọn 4K)

Trong mục **Resolution** có một menu **Source quality**: độ sắc nét của video được tải xuống từ YouTube. Trước đây nó cố định ở 720p, khiến các bản xuất 1080p/4K bị phóng to và mềm. Nay:

| Lựa chọn | Bạn nhận được | Đã đo (đoạn 20 giây của một video 4K) |
|---|---|---|
| **1080p (mặc định)** | H.264 1920x1080 | 10 MB |
| 4K | AV1/VP9 3840x2160, lớn hơn nhiều, giải mã chậm hơn | 70 MB |
| 1440p | ở giữa | |
| 720p | nhanh nhất, nhỏ nhất | 6 MB |

Nếu một video chỉ tồn tại ở 720p trên YouTube (một số video mới tải lên và nguồn chất lượng thấp), bạn nhận 720p dù chọn gì đi nữa. **Resolution** (kích thước xuất) là một cài đặt riêng: để xuất 4K sắc nét hãy chọn Source quality 4K và Resolution 2160. Nội dung nhập được lưu trong bộ nhớ đệm theo từng liên kết và tải lại nếu sau đó bạn yêu cầu chất lượng cao hơn.

## "Sign in to confirm you're not a bot" (kiểm tra bot của YouTube)

Một số kết nối nhận thông báo này từ YouTube: internet dùng chung hoặc dữ liệu di động, VPN, Wi-Fi văn phòng/ký túc xá, hoặc trình tải xuống đã cũ. NeonClipping xử lý giúp bạn theo thứ tự này, không cần cài đặt:

1. **Giữ yt-dlp luôn mới.** Mỗi ngày một lần khi khởi động, nó nâng cấp `yt-dlp[default]` (an toàn khi ngoại tuyến). Tắt bằng `NEONCLIPPING_NO_AUTOUPDATE=1`.
2. **Thử lại ở các chế độ YouTube khác** (TV, Safari, iOS, web di động) thay vì thất bại ngay lần chặn đầu tiên.
3. **Hiển thị một thông báo ngắn** với các cách khắc phục dưới đây thay vì một lỗi tiếng Anh dài dòng.

Nếu YouTube vẫn chặn bạn, hãy chọn một cách:

| Cách khắc phục | Cách làm |
|---|---|
| **Tải file MP4 lên** | Dùng **Upload video** cạnh hộp liên kết. Luôn hiệu quả. |
| **Dùng đăng nhập trình duyệt của bạn** | Đăng nhập YouTube trong Chrome (hoặc Edge / Firefox / Brave), rồi khởi động NeonClipping với `NEONCLIPPING_COOKIES_BROWSER=chrome`. PowerShell: `$env:NEONCLIPPING_COOKIES_BROWSER='chrome'; ./run.ps1`. Đóng trình duyệt trước nếu Windows báo file cookie bị khóa. |
| **Dùng file cookies** | Xuất `cookies.txt` từ trình duyệt và lưu nó thành `data/youtube_cookies.txt` (hoặc trỏ `NEONCLIPPING_COOKIES_FILE` vào nó). Nó ở lại trên máy của bạn. |
| **Đổi mạng** | Wi-Fi ở nhà thay vì dữ liệu di động; tắt VPN. |

Cookie chỉ được đọc khi bạn đặt một trong các tùy chọn trên; NeonClipping không bao giờ tự đọc trình duyệt của bạn. Dùng một tài khoản Google dùng một lần nếu bạn không muốn tài khoản chính của mình gắn với các lượt tải tự động. Python 3.10 đã bị yt-dlp ngừng hỗ trợ: dùng Python 3.11+ để các bản cập nhật tiếp tục đến. Mọi thứ liên quan đến YouTube đều đi qua [`ytdl.py`](ytdl.py).

## Giới hạn thật lòng

- Việc chọn điểm nhấn là một thuật toán phỏng đoán cộng một LLM cục bộ nhỏ. Nó tìm những khoảnh khắc ồn ào, giàu năng lượng, đáng trích dẫn, không đảm bảo "viral". Hãy xem lại trước khi đăng.
- Các tín hiệu hành động (chuyển động, chớp sáng, nhấp nháy đèn) là thuật toán phỏng đoán đơn giản trên một bản sao nhỏ độ phân giải thấp; chúng xếp hạng khoảnh khắc, chúng không nhận ra "một cuộc rượt đuổi của cảnh sát". Đánh giá sao là cách nó trở nên hợp gu của bạn hơn.
- LLM chỉ nhìn thấy văn bản. Nó không nhìn thấy màn hình.
- Không có phụ đề YouTube (VOD Twitch, file tải lên) thì một mô hình giọng nói phải chép lời từng ứng viên, việc này chậm trên CPU.
- Độ chính xác của phụ đề tự động đi theo nguồn: phụ đề tự động của YouTube không hoàn hảo, đặc biệt với Hinglish.
- Chế độ Deep mới chỉ được kiểm chứng trên một video ngắn; trên video nhiều giờ, nó tải toàn bộ file trước và chậm theo thiết kế.
- **Cắt clip trực tiếp:** mỗi lần một phiên live, và máy tính phải thức và có mạng trong khi ghi. Các phiên theo dõi creator không người trông dừng sau 3 giờ hoặc khi ổ đĩa còn trống dưới 8 GB (cả hai cấu hình được ở trên); một phiên thủ công thì không.
- **Đăng bài tùy chọn:** My clips → Publish a clip kết nối trực tiếp tới tài khoản YouTube, Instagram hoặc TikTok của chính bạn. Hàng đợi cục bộ xử lý lịch đăng. Xem phần thiết lập nền tảng bên dưới.
- **Ngôn ngữ phụ đề:** Hinglish, Hindi, English và 50 ngôn ngữ nữa (Whisper). Độ chính xác tốt nhất với các ngôn ngữ được nói rộng rãi. Phụ đề được vẽ bằng phông chữ đã cài trên máy của bạn, nên hệ chữ viết không có phông có thể hiện ô trống, và các ngôn ngữ viết phải-sang-trái (Arabic, Persian, Hebrew, Urdu) chỉ được hỗ trợ cơ bản. Khi YouTube cung cấp phụ đề bằng ngôn ngữ được nói, chúng được dùng thay cho mô hình giọng nói.
- Vị trí facecam đặt sẵn là điểm khởi đầu, không phải kết quả phát hiện: nếu bạn chọn Bottom-right nhưng cam ở dưới-trái, nửa trên của clip sẽ hiển thị sai vùng. Hãy chọn đúng góc hoặc tự vẽ khung của bạn.

## Ủng hộ

NeonClipping miễn phí. Nếu nó giúp bạn tiết kiệm thời gian, bạn có thể ⭐ star repo, theo dõi [@iamajmeena](https://www.instagram.com/iamajmeena/), hoặc tùy ý quyên góp qua Razorpay (UPI / thẻ): <https://rzp.io/rzp/JN41CpW>. Ứng dụng cũng có nút ♥ Donate. Không có gì bị khóa sau quyên góp cả.

## Ghi công và cảm hứng

Ý tưởng thiết kế được nghiên cứu từ các công cụ cắt clip mã nguồn mở: [PeakCut](https://github.com/haziqahmedqasmi/PeakCut) (tải ưu tiên âm thanh, phụ đề làm bản chép lời, tải theo đoạn), [ClipCutter](https://github.com/curtyo18/ClipCutter), [content-ai](https://github.com/buddah0/content-ai), và script cắt clip live Growlance. Cũng nghiên cứu: ý tưởng facecam-theo-viền-tĩnh và danh sách creator của PeakCut (được cài đặt lại ở đây bằng mã của chúng tôi, cộng thêm kiểm tra khuôn mặt), danh sách tính năng công khai của trình chỉnh sửa desktop YIZERGE (mẫu, thẻ nền, đoạn dâng nhạc, hoạt ảnh phụ đề; chỉ trang web công khai của nó được đọc), và phần hướng dẫn của một creator về việc chia một stream 9 giờ thành các phần bản chép lời nhỏ cho một chatbot miễn phí. Xây dựng trên FFmpeg, yt-dlp, FastAPI, faster-whisper, OpenCV (bộ phát hiện khuôn mặt YuNet, MIT), Ollama.

## Giấy phép

**AGPL-3.0** (từ ngày 24 tháng 11 năm 2026). Xem [LICENSE](LICENSE) và [NOTICE](NOTICE). Bạn có thể sử dụng, nghiên cứu, thay đổi và chia sẻ NeonClipping; nếu bạn chia sẻ một phiên bản đã thay đổi hoặc chạy nó cho người khác dưới dạng trang web hay dịch vụ, bạn cũng phải công bố toàn bộ mã nguồn của mình theo AGPL-3.0. Các phiên bản phát hành trước ngày 24 tháng 11 năm 2026 vẫn theo MIT. Đóng góp cần [CLA](CLA.md) (xem [CONTRIBUTING](CONTRIBUTING.md)). Để có giấy phép thương mại, hãy liên hệ tác giả. Tên và logo NeonClipping là thương hiệu của dự án.

## Thay đổi ngày 2026-11-21

- **Chất lượng tải xuống ngay cạnh nút Get preview.** 1080p là mặc định; chọn 4K, 1440p hoặc 720p ngay cạnh nút. Cài đặt 1080p không còn lùi về file mp4 720p làm sẵn của YouTube, và dòng tiến trình hiển thị luồng video/âm thanh, MB, tốc độ và thời gian còn lại.
- **Video rất dài (trên 2 giờ) không bao giờ được tải toàn bộ.** Một stream 24 giờ nặng khoảng 46 GB ở 1080p. Bạn chọn phần cần lấy (tối đa 2 giờ, h:mm:ss) và chỉ phần đó được tải xuống.
- **Bật/tắt tiêu đề mở đầu** (*Show opening heading on the clip*, bật theo mặc định). Tắt nghĩa là không có chữ tiêu đề, không hộp nền và không gọi mô hình cục bộ.
- **Sửa các vấn đề cài đặt đã được báo cáo:** shim cho PyAV 19 (`metadata_errors`) và ghim `av<19`, dự phòng FFmpeg di động và cảnh báo trên màn hình khi thiếu FFmpeg, trình cài đặt Windows dùng Python 3.10 đến 3.13 và cài Visual C++ runtime khi `ctranslate2.dll` không tải được, một dòng "working…" trực tiếp trong khi âm thanh dài đang được quét.
- **Report a problem** giờ cũng có trong thanh bên và phần đầu trang.
- Trên PC NVIDIA, nguồn cũng được giải mã trên GPU (NVDEC), với dự phòng tự động về CPU. Task Manager hiển thị việc này trong *Video Encode / Video Decode*, không phải *3D*.

## Cập nhật

NeonClipping giờ tự cập nhật. Khi có phiên bản mới trên GitHub, một biểu ngữ xanh lá xuất hiện ở đầu trang; nhấn **Update now**, hoặc để yên và nó tự cập nhật sau một đếm ngược ngắn khi không có gì đang chạy. Clip, cài đặt và các mô hình đã tải của bạn được giữ lại, một bản sao lưu của các file bị thay thế ở lại trong `.update-backup/`, và ứng dụng tự khởi động lại.

Nếu bạn đã cài một phiên bản cũ hơn, hãy chạy `NeonClipping-Setup.bat` thêm một lần nữa để có tính năng này. Sau đó không cần cài lại. Một bản git checkout không bao giờ bị trình cập nhật đụng vào (dùng `git pull`).

## Giao diện của tiêu đề mở đầu

Chọn **Heading look** ở bước 04: *Impact* (mặc định: chữ lớn đậm, một từ nhấn, pop-in, gạch chân hồng), *Neon glow*, *Banner bar* hoặc hộp bo tròn cổ điển. Mỗi clip hoàn thiện cũng có một **Cover image** (một khung hình sắc nét kèm tiêu đề) và file ZIP các clip chứa nó. Xem [CHANGELOG.md](CHANGELOG.md) để biết mọi thứ đã thay đổi.

## Cloud AI (tùy chọn)

Một PC chậm không có GPU có thể dùng mô hình đám mây thay cho Ollama để chấm điểm khoảnh khắc và viết tiêu đề cùng hook. Mở **Cloud AI (optional)** trên trang, chọn một nhà cung cấp (Groq, OpenRouter, Gemini, OpenAI hoặc LM Studio), dán key của bạn, nhấn **Test connection**, đánh dấu **Use Cloud AI** và Save. Việc chấm điểm gửi văn bản bản chép lời của ứng viên. Lập kế hoạch dòng thời gian gửi bản chép lời đã chọn và chỉ dẫn chỉnh sửa. Các lần gọi AI này chỉ gửi văn bản. Key được lưu trong `data/llm.json` trên máy của bạn và không bao giờ hiển thị lại. Chuyển giọng nói thành văn bản vẫn dùng phụ đề của YouTube hoặc mô hình cục bộ. Các biến môi trường `NEONCLIPPING_LLM_BASE_URL`, `NEONCLIPPING_LLM_MODEL` và `NEONCLIPPING_LLM_KEY` cũng hoạt động.

### Kết nối MCP cục bộ

Khởi động NeonClipping, rồi cấu hình MCP client của bạn với lệnh `uv` và các đối số `run`, `--script`, cùng đường dẫn tuyệt đối tới `neon_mcp.py`. Đầu nối stdio dùng máy chủ cục bộ trên cổng 8770 (ghi đè bằng NEONCLIPPING_PORT). Nó cung cấp create_clips, batch_status, resume_batch, list_clips, export_clip và download_clip. Các file tải xuống được ghi vào thư mục Downloads/NeonClipping của bạn.


### Timeline studio và khôi phục hàng loạt

Trong **My clips → Timeline studio**, thêm một bản xuất từ thư viện, nguồn hiện tại hoặc một video cục bộ. Chọn một đoạn, đặt điểm vào và ra của nó, hoặc tua và tách tại đầu phát. Di chuyển các đoạn lên để sắp xếp lại. Undo và redo áp dụng cho phiên chỉnh sửa hiện tại. Danh sách cắt sống sót qua lần tải lại trang trong cùng trình duyệt. Render and review tạo ra file MP4 1080×1920 cuối cùng. Export parts ghi một video riêng được đánh số cho từng đoạn.

Chuẩn bị một bản chép lời để lên kế hoạch một chủ đề, bản tóm tắt, series đánh số hoặc teaser. Edit by instruction có thể chọn, sắp xếp lại, punch in vào một đoạn hoặc áp dụng nguồn B-roll đã chọn. Các kế hoạch AI dùng mô hình văn bản được chọn trong NeonClipping. Cắt thủ công, loại bỏ tiếng ậm ừ khi nói, ước lượng người nói và hiệu ứng theo nhịp cũng hoạt động cục bộ. Chọn B-roll cho một đoạn, hoặc cấu hình tìm kiếm stock tùy chọn bằng NEONCLIPPING_PEXELS_KEY. Nhạc là tùy chọn và tự nhỏ xuống dưới âm thanh nguồn. Hãy xem lại file MP4 đã dựng để kiểm tra âm thanh hoàn chỉnh, các điểm đứng hình và bản phối hiệu ứng.

**Resume interrupted batch** khôi phục tác vụ Make thất bại gần nhất trong trình duyệt này. Queue Retry cũng tái sử dụng một điểm kiểm tra đã lưu. Siêu dữ liệu nguồn, âm thanh và các đoạn đã chọn đã lưu được tái sử dụng khi có. File bị thiếu phải được khôi phục hoặc bắt đầu lại hàng loạt từ đầu.

### Đăng trực tiếp lên nền tảng

Đặt thông tin xác thực ứng dụng nhà phát triển trên PC đang chạy NeonClipping, rồi mở **My clips → Publish a clip → Connect account**. Với mỗi nền tảng được bật, thay PLATFORM trong NEONCLIPPING_PLATFORM_CLIENT_ID và NEONCLIPPING_PLATFORM_CLIENT_SECRET bằng YOUTUBE, INSTAGRAM hoặc TIKTOK. Dùng TikTok client key làm client ID của nó. Đăng ký đúng URL callback. Mặc định là http://127.0.0.1:8770/social-callback. Đặt NEONCLIPPING_PLATFORM_REDIRECT_URI cho một callback đã duyệt khác. Với chuyển hướng tùy chỉnh, dán toàn bộ URL trả về vào Finish connection. Ứng dụng cục bộ trao đổi mã và lưu thông tin xác thực có thể gia hạn trong kho lưu trữ thông tin xác thực của hệ điều hành. Một NEONCLIPPING_PLATFORM_TOKEN tùy chọn ghi đè kết nối đã lưu. Hãy tự cập nhật token môi trường đã hết hạn.

- YouTube dùng các phạm vi upload và chỉ đọc. Chọn chế độ hiển thị của kênh trước khi gửi.
- Instagram dùng Instagram Login cho tài khoản chuyên nghiệp, với các quyền basic, publish và insights. Hãy đưa cho Meta một URL HTTPS truy cập công khai cho đúng Reel đã xuất. Máy chủ cục bộ không host file đó một cách công khai.
- TikTok dùng Login Kit và Content Posting API. Các lựa chọn hiển thị có sẵn đến từ tài khoản creator đã kết nối. Cấu hình các phạm vi user.info.basic, video.publish và video.list. Để triển khai công khai, hãy xác nhận các phê duyệt nền tảng của ứng dụng của bạn.
- Hàng đợi phải đang chạy vào thời điểm đã lên lịch. Khởi động muộn sẽ chạy các tác vụ đến hạn một lần khi hàng đợi tiếp tục. Hủy một bài đăng đang chờ trong bảng đăng bài. Một lần gửi mơ hồ được đánh dấu để kiểm tra trên nền tảng nhằm tránh trùng lặp tự động.
- Làm mới số liệu trên các bài đã gửi. Sau ít nhất sáu bài đủ lượt xem trên một tài khoản và hai ví dụ trong một nhóm độ dài, mức tương tác có thể so sánh được có thể điều chỉnh hạng ứng viên trong tương lai tối đa ba điểm phần trăm. Đánh giá sao cục bộ tiếp tục hoạt động riêng.
