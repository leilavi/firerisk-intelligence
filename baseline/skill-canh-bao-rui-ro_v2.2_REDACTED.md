---
name: "skill-canh-bao-rui-ro"
description: "skill cảnh báo rủi ro - giám sát vận hành và cảnh báo sớm rủi ro cho [Building] ([Operator]) - thiết bị, sự cố, điện, nước, dầu máy phát, bãi xe, lượt xe. Phát hiện bất thường và đột biến tăng/giảm, đối chiếu hoạt động, nêu nguyên nhân và hậu quả, dự báo rủi ro, lập báo cáo có ngày giờ lưu vào Drive, gửi email khi có Rủi ro cao/Khẩn cấp. LUÔN dùng skill này khi người dùng nhắc tới \"rủi ro\", \"cảnh báo\", \"cảnh báo rủi ro\", dự báo rủi ro, rủi ro vận hành, cảnh báo sớm, sự cố, bất thường, đột biến điện nước, báo cáo vận hành, dầu máy phát, bãi xe, dashboard vận hành, risk monitoring - kể cả khi không nói tên skill, chỉ hỏi một thiết bị, một chỉ số hoặc một cảnh báo."
---

# SKILL CẢNH BÁO RỦI RO – [OPERATOR] [BUILDING]

Tên skill: **skill cảnh báo rủi ro** (mã kỹ thuật `skill-canh-bao-rui-ro`; tên cũ `operator-operations-risk-monitor`).
Phiên bản: 2.2 (08/10/2026 14:10 GMT+7). Giữ nguyên toàn bộ logic bản 2.1; **chốt mẫu trình bày báo cáo**: mọi báo cáo phải dựng từ file mẫu đã chốt (mục 11.2, bắt buộc), thêm mức Khẩn cấp trong mẫu, cách tải file nguồn lớn (mục 2.2). Bản 2.1 (07/10/2026 15:48) bổ sung tự kích hoạt theo từ khóa (mục 0.1) và quy tắc lưu skill, báo cáo có ngày giờ (mục 0.2, 1, 14). Thay thế bản 1.0 và phần "Bổ sung phân tích chi phí vận hành và doanh thu bãi xe".

## 0. Mục tiêu cao nhất

Skill này là công cụ **cảnh báo sớm**: tìm dấu hiệu báo trước sự cố, chứng minh bằng dữ liệu, giải thích nguyên nhân, nêu hậu quả nếu không hành động và thúc đẩy biện pháp phòng ngừa trước khi sự cố xảy ra.

Ưu tiên **độ chính xác và giá trị hành động** hơn số lượng cảnh báo hay vẻ ngoài của dashboard. Một cảnh báo đúng, có nguyên nhân và hậu quả rõ ràng có giá trị hơn mười cảnh báo chung chung.

Mọi cảnh báo phải trả lời được ba câu hỏi:

1. **Điều gì có thể xảy ra?**
2. **Tại sao cần quan tâm ngay bây giờ?**
3. **Phải làm gì để ngăn chặn trước khi quá muộn?**

Skill dùng các file hiện có làm nguồn gốc; chỉ đọc dữ liệu gốc; không xây dựng lại hệ thống quản lý tài sản; không yêu cầu nhập lại dữ liệu đã có; không bịa số liệu, ngưỡng, định mức, chi phí, trạng thái, nguyên nhân hay thời điểm sự cố.

### 0.1 Kích hoạt tự động theo từ khóa

Claude phải **tự động hiểu và kích hoạt "skill cảnh báo rủi ro"**, không cần người dùng nói đúng tên skill, khi tin nhắn có một trong các từ khóa hoặc ý sau (không phân biệt hoa thường, có dấu hay không dấu):

| Nhóm | Ví dụ cách người dùng nói |
|---|---|
| **rủi ro** | "rủi ro", "rui ro", "đánh giá rủi ro", "dự báo rủi ro", "có rủi ro gì không", "rủi ro vận hành", "rủi ro thiết bị" |
| **cảnh báo** | "cảnh báo", "canh bao", "có cảnh báo nào không", "cảnh báo sớm", "gửi cảnh báo", "kiểm tra cảnh báo" |
| **cảnh báo rủi ro** | "cảnh báo rủi ro", "báo cáo cảnh báo rủi ro", "chạy cảnh báo rủi ro", "cập nhật cảnh báo rủi ro" |
| Ý tương đương | sự cố sắp xảy ra, bất thường, đột biến điện/nước, thiết bị có nguy cơ hỏng, tình hình vận hành [Building] |

Khi kích hoạt, chạy đầy đủ quy trình của skill này:
- Thu thập và kiểm tra dữ liệu (mục 2, 4).
- Phát hiện vấn đề và đột biến tăng/giảm (mục 4, 5, 5A).
- Đối chiếu hoạt động, áp dụng 7 bước và xếp mức độ (mục 5–7).
- Viết cảnh báo đủ 14 trường (mục 8) và dự báo rủi ro (mục 9).
- Gửi email theo điều kiện (mục 10).
- Lập và lưu báo cáo mới có ngày giờ (mục 0.2, 14).

Người dùng chỉ hỏi một thiết bị, một chỉ số hay một cảnh báo thì vẫn dùng logic này, giới hạn phạm vi theo câu hỏi (Giai đoạn 1 mục 5), và vẫn nêu ngắn rủi ro cao ngoài phạm vi.

Không kích hoạt khi từ khóa rõ ràng thuộc chủ đề khác không liên quan tới vận hành tòa nhà, ví dụ "rủi ro đầu tư chứng khoán" hay "cảnh báo thời tiết" hỏi chung. Nếu không chắc, hỏi lại một câu ngắn.

### 0.2 Nơi lưu skill và báo cáo trên Google Drive

| Thư mục | ID | Nội dung | Quy tắc |
|---|---|---|---|
| `Skill` (trong "[BUILDING]") | `<REDACTED_DRIVE_ID>` | `skill.md` – phiên bản skill mới nhất; `mau_bao_cao_canh_bao_rui_ro.html` – **mẫu báo cáo đã chốt** (mục 11.2) | Khi cập nhật skill: đổi tên file cũ thành `skill_luu_DD-MM-YYYY_HHhMM.md`, rồi tạo `skill.md` mới. Không xóa bản cũ |
| `Cảnh báo rủi ro` (trong "[BUILDING]") | `<REDACTED_DRIVE_ID>` | Báo cáo cảnh báo rủi ro mỗi lần chạy | Mỗi lần chạy tạo **file mới**, không ghi đè, không xóa báo cáo cũ |

- Mỗi lần chạy, tìm lại thư mục theo ID. Không thấy thì tìm theo tên (`Skill`, `Cảnh báo rủi ro`). Vẫn không có thì tạo thư mục mới trong "[BUILDING]" và báo ID mới cho người dùng.
- **Tên file báo cáo:** `Bao_cao_canh_bao_rui_ro_DD-MM-YYYY_HHhMM.html`, ví dụ `Bao_cao_canh_bao_rui_ro_07-10-2026_15h48.html`. Thời điểm là lúc báo cáo được tạo hoặc cập nhật, theo GMT+7. Nếu đã có file trùng tên thì thêm `_v2`, `_v3`, không ghi đè.
- **Trong nội dung báo cáo** phải ghi "Lập lúc: DD/MM/YYYY HH:mm (GMT+7)" ở đầu trang. Ghi riêng ngày đọc dữ liệu mới nhất của từng nguồn.
- Báo cáo mới nhất là file có ngày giờ lớn nhất trong tên. Khi trả lời người dùng, nêu tên file và ID vừa tạo.

## 1. Đặc tả kết quả

- **Định dạng:** dashboard HTML (KPI, biểu đồ, bảng, màu theo mức độ), **dựng từ mẫu đã chốt ở mục 11.2 – không tự thiết kế giao diện mới**. Không tạo được HTML thì xuất Markdown có cấu trúc. Không tuyên bố đã tạo file nếu file chưa tồn tại.
- **Ngôn ngữ:** tiếng Việt. **Giọng điệu:** chuyên nghiệp, trực diện, dựa trên dữ liệu.
- **Đối tượng:** Ban Giám đốc, Ban quản lý tòa nhà, bộ phận kỹ thuật, kế toán, bãi xe.
- **Múi giờ:** Asia/Ho_Chi_Minh (GMT+7). Mọi thời điểm ghi kèm múi giờ.
- **Tên file:** `Bao_cao_canh_bao_rui_ro_DD-MM-YYYY_HHhMM.html` (mục 0.2); trùng giờ thì thêm hậu tố `_v2`, `_v3`. Đầu báo cáo ghi "Lập lúc: DD/MM/YYYY HH:mm (GMT+7)".
- **Kỳ phân tích:** mặc định từ đầu năm đến dữ liệu mới nhất đọc được; người dùng chỉ định kỳ thì theo kỳ đó.
- **Độ dài:** tổng quan ngắn gọn; phần chi tiết đủ bằng chứng để người đọc tự kiểm tra.

## 2. Nguồn dữ liệu cố định

### 2.1 Bản đồ nguồn

| Nguồn | File ID | Nội dung | Ghi chú |
|---|---|---|---|
| Google Sheet "Operations Data" | `<REDACTED_DRIVE_ID>` | Tab `chỉ số điện nước`, `BC hư hỏng TS`, `NK thi công - sự cố`, `Dầu M Phát điện` | Tab hư hỏng và sự cố dùng chung nhiều chi nhánh [Operator] |
| Thư mục vận hành | `<REDACTED_DRIVE_ID>` | `Theo dõi chi phí điện`, `Theo dõi chi phí nước`, `Theo dõi doanh thu bãi xe`, `Theo dõi lượt khách ra vào` (.xlsx) | Liệt kê lại toàn bộ file mỗi lần chạy, kể cả file mới |
| Thư mục "[BUILDING]" | `<REDACTED_DRIVE_ID>` | Sheet `OPERATOR_Alert_Log`, `OPERATOR_Danh_muc_dong_ho`; chứa hai thư mục con `Skill` và `Cảnh báo rủi ro` | Chỉ tạo file mới; không ghi đè file người khác |
| Thư mục "Cảnh báo rủi ro" | `<REDACTED_DRIVE_ID>` | Báo cáo cảnh báo rủi ro mỗi lần chạy (mục 0.2) | Mỗi lần một file mới có ngày giờ |
| Thư mục "Skill" | `<REDACTED_DRIVE_ID>` | `skill.md` bản mới nhất; `mau_bao_cao_canh_bao_rui_ro.html` mẫu báo cáo đã chốt | Bản cũ đổi tên, không xóa |

Danh sách file là trạng thái đã xác minh ngày 07/10/2026. Mỗi lần chạy phải liệt kê lại thư mục; file nào mới xuất hiện thì đọc và đưa vào phân tích nếu liên quan.

### 2.2 Cách đọc

- **Không** dùng `read_file_content` để phân tích: công cụ này chỉ trả về khoảng 10 dòng mẫu mỗi tab.
- Google Sheet: `download_file_content` với `exportMimeType = application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. File .xlsx: `download_file_content` không cần exportMimeType. Nếu kết quả quá dài và được lưu ra file, đọc file đó, giải mã base64 vào thư mục làm việc, mở bằng openpyxl (`data_only=True`) hoặc pandas.
- **File lớn (đã gặp 08/10/2026):** bản xuất .xlsx của Google Sheet có thể bị cắt ở khoảng 100.000 ký tự. Khi đó xuất bằng `exportMimeType = application/vnd.oasis.opendocument.spreadsheet` (ODS): kết quả được lưu ra file JSON `{content: base64}`; giải mã rồi chuyển sang xlsx bằng `soffice --headless --convert-to xlsx`. Kiểm tra số dòng mỗi tab không dừng ở mức tròn (500, 1.000) và bản ghi mới nhất khớp `modifiedTime`.
- Ghi nhận cho từng nguồn: `modifiedTime` của file, ngày bản ghi mới nhất của từng tab, số dòng đã đọc. Ba thông tin này khác nhau và phải trình bày riêng.
- Nếu một nguồn không đọc được: nêu nguyên nhân kiểm tra được (chưa kết nối, thiếu quyền, không tồn tại, lỗi công cụ), nói rõ phần phân tích bị ảnh hưởng, vẫn hoàn thành phần còn lại. Không thay bằng số liệu giả định.

### 2.3 Phạm vi và lọc

- Chỉ phân tích bản ghi của [Building]: `Location_ID` hoặc `Chi Nhánh` bắt đầu bằng `BLD`, hoặc `Equipment_ID` có tiền tố `P-`. Loại SITE-2, SITE-3 và chi nhánh khác. Báo cáo số dòng đã loại.
- Bản ghi thử (chứa "Test", "Chỉ test", "TEST", tên KTV giữ chỗ như "Hãy nhập…", "Tên KTV sửa chữa?", "AAAAA"): gắn cờ, đếm, không tính vào thống kê. Ngoại lệ: bản ghi thử mô tả rủi ro an toàn (thang máy, điện, PCCC, máy phát) vẫn đưa vào bảng cảnh báo với trạng thái "Chưa xác minh – cần xác nhận thật hay thử".
- Chưa có danh mục tài sản (mã – tên – vị trí – hệ thống – đơn vị đo) thì không suy đoán tên thiết bị từ mã; ghi "Chưa xác định tên thiết bị".

### 2.4 Đặc điểm từng nguồn đã biết

- **Danh mục đồng hồ `OPERATOR_Danh_muc_dong_ho`** (Google Sheet trong thư mục báo cáo, tạo 07/10/2026): mỗi lần chạy phải đọc trước khi phân tích đồng hồ. Dùng `ten_dong_ho`, `don_vi_do`, `pham_vi_do_khu_vuc_phu_tai`, `nam_sau_dong_ho_EVN_TTC076`, `he_so_nhan_CT` để gọi tên và đánh giá từng đồng hồ. Chỉ coi là đã xác minh khi `nguoi_xac_nhan` có giá trị; dòng còn "CHƯA XÁC ĐỊNH" thì báo cáo ghi "Chưa xác định tên", không tự đặt tên, và nhắc BQL điền. Đồng hồ mới xuất hiện trong nhật ký mà chưa có trong danh mục thì liệt kê để bổ sung. Không ghi vào sheet này trừ khi người dùng yêu cầu.
- **`chỉ số điện nước`**: đọc hằng ngày ca 1. `Chỉ_Số_Thiết_Bị` là **số đọc công tơ tích lũy**, `Tiêu_Thụ_Ngày` là lượng tiêu thụ trong ngày do người nhập. Tên đồng hồ điện do người dùng xác nhận 07/10/2026: `P-BG.TTC076` **đồng hồ điện lực (EVN)**, kWh = chỉ số × 100 (đã khớp hóa đơn 99,9% ở kỳ 11–20/07 và 11–20/08); `P-BG.TTC071` **đồng hồ MSB** (≈ 97% EVN); `P-BG.TTC078` máy lạnh tầng 2; `P-BG.TTC042` máy lạnh tầng 3 (đổi mã hệ thống từ `J-HT -010` sang `C-HT-011` ngày 16/07/2026); `P-BG.TTC104` năng lượng mặt trời; `P-BG.TTC226` xử lý nước thải. Đơn vị của 4 đồng hồ phụ chưa xác minh. Đã xác minh từ nguồn: `P-BG.TTC172` đồng hồ nước tổng (m³); `P-BG.TTC017` mức dầu máy phát (L). **Biểu đồ điện theo ngày so với lượt xe/ngày phải dùng `TTC076` (EVN), không dùng `TTC071`**; `TTC071` vẽ riêng để so với EVN (tổn hao, lỗi đọc). Đồng hồ đọc khoảng 6 giờ sáng: lượng tăng từ sáng ngày d đến sáng ngày d+1 ghi cho **ngày tiêu thụ d** trước khi so với lượt xe hay sự kiện.
- **`BC hư hỏng TS`**: hồ sơ sửa chữa/bảo trì; `Actual_Cost` phần lớn trống; người duyệt đổi từ 16/09/2026.
- **`NK thi công - sự cố`**: gồm "Báo cáo sự cố" và "Nhật ký thi công". Trạng thái "Đang thi công" có thể không được cập nhật sau ngày hoàn thành.
- **`Dầu M Phát điện`**: bồn 3.000 L (suy từ `%_Nhiên_liệu_tồn`), thước đọc bước 10 L. Kiểm tra năm sai, thời lượng 00:00 dù giờ bắt đầu khác giờ kết thúc, bản ghi chồng giờ, lệch với số đọc `P-BG.TTC017`. `Giá_NL_TB` phải lấy từ hóa đơn nhập dầu; không đổi nhiều tháng thì gắn nhãn "chi phí ước tính".
- **`Theo dõi chi phí điện`**: mỗi kỳ gồm 3 dòng biểu giá (BT bình thường, CĐ cao điểm, TĐ thấp điểm), dòng "Cộng", "VAT 8%", "Tổng cộng". Dòng đầu kỳ cuối tháng chứa kWh, tiền phải thu và đã thu từ khách thuê (kỳ chốt 26 tháng trước – 25 tháng này). Kiểm tra kỳ lặp, STT, ngày không hợp lệ, cột "Đã thu" bị sao chép, tháng thiếu phải thu.
- **`Theo dõi chi phí nước`** (Sheet3): chuỗi chỉ số liên tục, kỳ chốt ngày 09; tách khách thuê và khu công cộng. Dòng tổng có thể không gồm kỳ cuối; tự cộng lại.
- **`Theo dõi doanh thu bãi xe`**: mỗi tháng một sheet, có "Số thực tế" và "Số hệ thống". Kiểm tra tên sheet khớp kỳ trong tiêu đề.
- **`Theo dõi lượt khách ra vào`**: "lượt khách" là **số ước tính** (ô tô × 4, xe máy × 2, cộng khách vãng lai ước lượng; cách ước lượng thay đổi theo tháng). "Lượt xe" (SL xe ô tô, SL xe máy) là số đếm thực tế. Dùng **lượt xe** làm mẫu số cho mọi tỷ lệ hiệu suất; lượt khách chỉ để tham khảo và phải ghi rõ là ước tính.

## 3. Thuật ngữ, số liệu và giá trị hiệu chỉnh

### 3.1 Quy tắc giải thích thuật ngữ

Mọi thuật ngữ viết tắt, tên trường dữ liệu, chỉ số tính toán và cụm từ chuyên môn có ảnh hưởng đến quyết định phải được giải thích **tại lần xuất hiện đầu tiên** trong báo cáo hoặc trong bảng thuật ngữ có liên kết từ phần tổng quan. Không tự điền giải thích khi chưa có bằng chứng; khi đó ghi "Chưa xác minh".

Báo cáo luôn có **Bảng thuật ngữ** với các cột: thuật ngữ gốc · diễn giải · đơn vị · nguồn (file/sheet/cột) · công thức nếu có · dùng để làm gì trong báo cáo · tình trạng xác minh (Đã xác minh từ nguồn / Do Claude tính / Chưa xác minh).

Bảng thuật ngữ tối thiểu:

| Thuật ngữ | Diễn giải | Đơn vị | Nguồn | Tình trạng |
|---|---|---|---|---|
| BT / CĐ / TĐ | Giờ bình thường / cao điểm / thấp điểm theo biểu giá điện | kWh, đ/kWh | Theo dõi chi phí điện, cột "ĐIỆN NĂNG TIÊU THỤ", "ĐƠN GIÁ" | Đã xác minh |
| Số đọc công tơ | Giá trị tích lũy trên đồng hồ tại thời điểm đọc | kWh, m³, L | `Chỉ_Số_Thiết_Bị`, "Chỉ số cũ/mới", "Số cũ/mới" | Đã xác minh |
| Tiêu thụ ngày | Chênh lệch hai số đọc liên tiếp chia số ngày giữa hai lần đọc | kWh/ngày, m³/ngày | Do Claude tính từ `Chỉ_Số_Thiết_Bị`; đối chiếu `Tiêu_Thụ_Ngày` | Do Claude tính |
| Đơn giá bình quân | Tổng tiền (gồm VAT) / tổng sản lượng cùng kỳ | đ/kWh, đ/m³ | Do Claude tính | Do Claude tính |
| Khu vực công cộng | Phần sản lượng không thu lại từ khách thuê | kWh, m³ | Cột "ĐIỆN KHU VỰC CÔNG CỘNG", "KHU VỰC CÔNG CỘNG" | Đã xác minh tên cột; phương pháp tính chưa xác minh |
| Lượt khách | Số ước tính từ lượt xe và khách vãng lai ước lượng | lượt | Theo dõi lượt khách | Ước tính, phương pháp thay đổi |
| Suất tiêu hao dầu | Lít dầu tiêu thụ / giờ chạy máy | L/giờ | Do Claude tính, chỉ cho lần chạy ≥ 2 giờ | Do Claude tính |
| MSB / MBA | Tủ điện tổng hạ thế / máy biến áp | – | BC hư hỏng TS | Đã xác minh từ mô tả |
| XLNT | Hệ thống xử lý nước thải | – | NK sự cố | Đã xác minh |

### 3.2 Giá trị "hiệu chỉnh" (kWh hiệu chỉnh, điện hiệu chỉnh, số hiệu chỉnh…)

**Trạng thái đã xác minh ngày 07/10/2026:** không có trường, cột hay bản ghi nào trong 5 nguồn mang tên "kWh hiệu chỉnh", "điện hiệu chỉnh" hoặc tương tự (đã quét toàn bộ ô văn bản). Cụm từ "kWh đã hiệu chỉnh" trong báo cáo ngày 07/10/2026 là **giá trị do Claude tự ước tính** khi chuyển 11.769 kWh giữa T7 và T8 dựa trên đồng hồ `P-BG.TTC071` (bản sau dùng đồng hồ EVN `P-BG.TTC076`: T7 64.243, T8 64.126, T9 61.876 kWh – vẫn là ước tính, chưa xác nhận); đó không phải số liệu nghiệp vụ và chưa được ai xác nhận. Từ phiên bản này, không được dùng nhãn "hiệu chỉnh" cho giá trị tự tính.

Mỗi lần chạy phải quét lại các nguồn tìm các từ "hiệu chỉnh", "điều chỉnh", "adjusted", "quy đổi", "ước tính" trong tên cột và ghi chú.

**A. Nếu nguồn có giá trị hiệu chỉnh**, trước khi dùng phải xác định và ghi trong bảng truy vết:

1. File, sheet, cột, dòng chứa giá trị; tên trường nguyên gốc.
2. Đơn vị đo và kỳ thời gian.
3. Giá trị gốc, giá trị sau hiệu chỉnh, chênh lệch tuyệt đối và %.
4. Công thức hoặc phương pháp tạo ra giá trị hiệu chỉnh.
5. Lý do; người hoặc bộ phận xác nhận nếu nguồn ghi nhận.
6. Loại hiệu chỉnh: thay đổi cách tính, sửa lỗi nhập liệu, điều chỉnh phạm vi, quy đổi đơn vị, ước tính hay khác.
7. Giá trị nào được dùng cho biểu đồ, KPI, so sánh và cảnh báo.

Nếu nguồn không giải thích: ghi nguyên văn **"Chưa xác minh được ý nghĩa và cơ sở của giá trị hiệu chỉnh"**, kèm yêu cầu xác minh cụ thể (ai cần trả lời, câu hỏi gì, hạn nào). Không suy đoán ý nghĩa từ tên cột.

**B. Giá trị Claude tự ước tính** (ví dụ phân bổ lại sản lượng khi chỉ số chốt kỳ có dấu hiệu sai): gọi đúng tên **"Ước tính phân bổ lại kỳ (do Claude tính, chưa xác nhận)"**, ghi rõ phương pháp, dữ liệu dùng để tính và sai số có thể có.

**C. Quy tắc sử dụng (áp dụng cho cả A và B):**

- KPI, biểu đồ chính, so sánh kỳ và email dùng **giá trị gốc**. Giá trị hiệu chỉnh hoặc ước tính chỉ được hiển thị bên cạnh, có nhãn và chú thích.
- Không tự thay giá trị gốc bằng giá trị hiệu chỉnh hoặc ngược lại khi chưa hiểu cơ sở nghiệp vụ. Giữ cả hai, ghi trạng thái.
- Không dùng giá trị chưa xác minh để tạo kết luận rủi ro quan trọng hay phát email.
- Nếu hai giá trị dẫn đến kết luận khác nhau (ví dụ tăng 8,4% theo gốc nhưng giảm 10,6% theo ước tính), phải trình bày cả hai kịch bản và đánh dấu kết luận "Chưa đủ cơ sở" cho đến khi xác minh.

## 4. Quy trình – 5 giai đoạn

### Giai đoạn 1 – Thu thập

1. Liệt kê thư mục vận hành; tải toàn bộ file liên quan và cả 4 tab của sheet chính (mục 2.2).
2. Ghi `modifiedTime`, ngày dữ liệu mới nhất, số dòng đọc được cho từng nguồn.
3. Lọc phạm vi [Building] và bản ghi thử (mục 2.3).
4. Liên kết dữ liệu bằng mã thiết bị, ngày, kỳ. Không ghép dựa trên tên gần giống; trường hợp không chắc đưa vào danh sách cần xác minh.
5. Người dùng chỉ định kỳ hoặc nhóm thiết bị thì giới hạn phạm vi, nhưng vẫn nêu ngắn rủi ro cao ngoài phạm vi.

Không hỏi lại thông tin đã có trong nguồn. Chỉ hỏi khi thiếu thông tin mang tính quyết định.

### Giai đoạn 2 – Kiểm tra chất lượng dữ liệu (chung)

Kiểm tra trước khi phân tích: ngày thiếu, sai định dạng, không theo thứ tự; bản ghi trùng; mã không khớp giữa các file; đơn vị hoặc cách ghi thay đổi; số âm, bằng 0, tăng giảm vô lý; chênh lệch số đầu kỳ – cuối kỳ – lượng tiêu thụ; dòng tổng không khớp tổng chi tiết; tab dừng cập nhật. Chỉ chuẩn hóa trên bản sao, ghi rõ quy tắc, giữ nguyên giá trị nguồn.

### Giai đoạn 2B – Kiểm tra dữ liệu đồng hồ điện, nước hằng ngày

Bắt buộc mỗi lần chạy, cho **từng đồng hồ** trong tab `chỉ số điện nước`:

1. Ngày đọc đồng hồ mới nhất (từ `Thời_Điểm_Kiểm_Tra`).
2. Ngày file được sửa (`modifiedTime`) và thời điểm lập báo cáo – trình bày tách biệt với ngày đọc.
3. Lập lịch ngày đầy đủ từ ngày đọc đầu tiên đến ngày lập báo cáo; đánh dấu từng ngày: có dữ liệu / thiếu / trùng (nhiều lần đọc cùng ngày) / giá trị chưa hợp lý.
4. Tính tiêu thụ ngày = (số đọc sau − số đọc trước) / số ngày giữa hai lần đọc. Khoảng cách > 1,5 ngày thì chia đều cho số ngày và đánh dấu "bình quân qua khoảng trống", không gán cho một ngày.
5. Đối chiếu kết quả với cột `Tiêu_Thụ_Ngày`; ghi số ngày lệch > 1 đơn vị.
6. Số đọc giảm: kiểm tra thay đồng hồ, đặt lại, quay vòng (rollover), đổi mã, lỗi nhập trước khi kết luận; chưa rõ thì loại điểm đó khỏi tính toán và ghi vào danh sách cần xác minh.
7. Ngày có tiêu thụ gần 0 rồi ngày sau tăng gấp đôi trở lên: kiểm tra ghi trễ (ví dụ đồng hồ MSB `TTC071` ngày tiêu thụ 13–14/08/2026: 16 kWh rồi 3.857 kWh, trong khi EVN `TTC076` bình thường).
8. Kiểm tra tổng theo tuần/tháng/kỳ hóa đơn bằng tổng dữ liệu ngày; so với hóa đơn cùng kỳ. Lệch > 15% ở hai kỳ liền kề theo chiều ngược nhau là dấu hiệu sai chỉ số chốt kỳ (ví dụ hóa đơn 21–31/07 và 01–10/08/2026: thừa 11.027 rồi thiếu 11.028 kWh so với đồng hồ EVN `TTC076`). So hóa đơn với `TTC076`, không với `TTC071`.
9. Không có bản ghi mới > 2 ngày so với ngày lập báo cáo: tạo cảnh báo dữ liệu (nhóm Dữ liệu) và nói rõ phần phân tích bị ảnh hưởng. Trước khi kết luận "ngừng nhập", đếm số dòng của tab. Nếu số dòng tròn (500, 1.000, 5.000…), mọi đồng hồ dừng cùng một thời điểm trong khi các tab khác vẫn cập nhật, thì nêu giả thuyết **giới hạn dòng khi xuất** và đề nghị xuất lại toàn bộ hoặc đọc bảng gốc (ví dụ 07/10/2026: tab có đúng 500 dòng, dừng ở sáng 10/09/2026).
10. Đối chiếu số liệu ngày với KPI, biểu đồ, bảng cảnh báo và phần nhận định (Giai đoạn 4, mục 13).

**Quy tắc biểu đồ điện, nước:**

- Có dữ liệu ngày thì vẽ chuỗi theo ngày; trục X là **lịch ngày đầy đủ** của khoảng phân tích, không phải danh sách ngày có dữ liệu.
- Ghi nhãn ngày, đơn vị, khoảng thời gian, mã đồng hồ.
- Mỗi đồng hồ là một chuỗi hoặc một biểu đồ riêng theo mã hiện có. Không cộng gộp các đồng hồ khi chưa xác minh phạm vi đo.
- Ngày thiếu để giá trị `null` và **không nối đường** qua khoảng trống (Chart.js: `spanGaps: false`); tô vùng hoặc ghi chú "thiếu dữ liệu" và liệt kê ngày thiếu dưới biểu đồ.
- Không biến giá trị thiếu thành 0; không lặp lại giá trị cũ để lấp ngày trống.
- Phân biệt biểu đồ số đọc công tơ (tích lũy) và biểu đồ tiêu thụ ngày; không vẽ lẫn.
- Không bỏ ngày có dữ liệu hợp lệ vì khó trình bày. Điểm ngoại lai giữ nguyên, đánh dấu màu, có chú thích.
- Nếu số điểm trên biểu đồ ít hơn số ngày có dữ liệu trong nguồn, phải tìm nguyên nhân thực tế (lọc sai ngày, lỗi định dạng ngày, đọc thiếu tab, giới hạn dòng, `dropna` loại nhầm cột, lỗi JavaScript) và sửa trước khi bàn giao. Không chấp nhận giải thích chung "dữ liệu chưa đầy đủ" khi dữ liệu thực tế đã tồn tại.

### Giai đoạn 2C – Phân tích chuyên đề

**A. Thiết bị, sự cố, bảo trì:** sự cố lặp lại trên cùng thiết bị; tần suất tăng; khoảng cách giữa các lần hỏng rút ngắn; lỗi tái diễn sau sửa chữa; sự cố chưa đóng hoặc quá hạn; nhiều thiết bị cùng hệ thống lỗi trong thời gian ngắn; thiết bị trọng yếu (điện, máy phát, PCCC, thang, XLNT) có hồ sơ xuống cấp hoặc kiểm tra không đạt; thiếu hồ sơ bảo trì. Mỗi phát hiện ghi mã thiết bị, thời điểm, số lần, lịch sử, bằng chứng. Không mặc định thiết bị hay hỏng là phải thay.

**B. Điện – sản lượng và chi phí:** tổng hợp kWh và tiền (gồm VAT) theo kỳ và tháng; so kỳ trước, cùng kỳ nếu có; mức tăng giảm tuyệt đối và %; đơn giá bình quân; tỷ trọng giờ cao điểm; tách biến động do sản lượng và do đơn giá; kWh/ngày; kWh và tiền trên mỗi lượt xe; đối soát phải thu – đã thu tiền điện khách thuê.

**C. Nước – sản lượng và chi phí:** m³ và tiền theo kỳ; m³/ngày; khách thuê và khu công cộng; tiêu thụ ngày từ `TTC172`; đơn giá bình quân; đối soát phải thu – đã thu. Không kết luận rò rỉ từ một lần tăng.

**D. Dầu máy phát:** tồn đầu – nhập – tiêu thụ – tồn cuối; giờ chạy; số lần mất điện lưới; suất tiêu hao cho lần chạy ≥ 2 giờ; số giờ chạy liên tục còn đáp ứng = tồn hiện tại / khoảng suất tiêu hao quan sát được; kịch bản tồn dầu. Không tự tạo định mức L/giờ; không tự đặt mức tồn tối thiểu.

**E. Doanh thu bãi xe:** theo tháng và cơ cấu (vãng lai, vé tháng, [Tenant A], vé giấy, mất thẻ); so kỳ; doanh thu/lượt xe; chênh lệch "Số thực tế" – "Số hệ thống" trên các dòng có cả hai số và xu hướng chênh lệch; ngày thiếu ghi nhận. Không suy luận thất thoát hay sai phạm; chỉ nêu nội dung cần đối soát.

**F. Lượt xe và hiệu suất:** lượt xe/ngày trên số ngày có dữ liệu; liệt kê ngày thiếu; kWh/lượt xe, m³/lượt xe, doanh thu/lượt xe. Tháng thiếu > 20% số ngày không dùng làm kỳ so sánh.

**Công thức:** biến động % = (kỳ hiện tại − kỳ so sánh) / kỳ so sánh × 100; đơn giá bình quân = tiền / sản lượng cùng kỳ; tỷ lệ trên lượt xe = chỉ số trong kỳ / lượt xe cùng kỳ. Chỉ tính khi cùng kỳ, cùng phạm vi; không chia cho 0. Không gọi chênh lệch giữa doanh thu bãi xe và chi phí điện nước là lợi nhuận.

## 5. Đối chiếu hoạt động trước khi phát cảnh báo

Không phát cảnh báo chỉ vì một chỉ số tăng hoặc giảm.

**Điện tăng** → kiểm tra cùng kỳ: lượt xe; giờ hoạt động, lịch vận hành; thay đổi thiết bị, khu vực, khách thuê, thi công (NK thi công); lịch sử các ngày tương ứng (cùng thứ trong tuần); kWh/lượt xe so với phạm vi lịch sử; chất lượng dữ liệu, cách đọc đồng hồ, giá trị hiệu chỉnh.

- Điện tăng tương ứng với lượt xe, kWh/lượt xe vẫn trong phạm vi lịch sử, không có dấu hiệu khác → **Biến động hợp lý**, không tạo cảnh báo (có thể ghi một dòng trong phần phân tích).
- Điện tăng mạnh khi lượt xe không tăng tương ứng, hoặc kWh/lượt xe vượt phạm vi lịch sử, hoặc có dấu hiệu khác (tăng vào giờ đóng cửa, tăng giờ cao điểm) → tiếp tục tìm bằng chứng, nêu giả thuyết, cân nhắc cảnh báo.
- Không mặc định lượt xe tăng luôn giải thích được điện tăng; so sánh độ lớn, thời gian, phạm vi.

**Nước tăng** → kiểm tra lượt xe, hoạt động vệ sinh, xả bồn, thi công, lịch sử. Tăng tương xứng hoạt động và trong phạm vi hợp lý → không kết luận rò rỉ. Tăng bất thường so với hoạt động, kéo dài nhiều ngày, xảy ra khi ít hoạt động, hoặc kết thúc đột ngột → nêu giả thuyết (rò rỉ, van, phao bồn, đồng hồ, thi công) và bước kiểm tra phân biệt từng giả thuyết.

**5A. Phát hiện đột biến điện, nước – cả tăng và giảm (bắt buộc mỗi lần chạy)**

Áp dụng cho **từng đồng hồ** điện, nước có tiêu thụ ngày (Giai đoạn 2B), cho mọi ngày từ lần chạy trước đến ngày đọc mới nhất. Lần chạy đầu thì quét toàn kỳ.

1. **Ngày tiêu thụ:** đồng hồ đọc khoảng 6 giờ sáng, nên lượng tăng từ sáng ngày d đến sáng ngày d+1 ghi cho ngày d. Khoảng đọc lệch hơn 6 giờ so với 24 giờ thì quy về 1 ngày (Δ / số ngày) và đánh dấu.
2. **Đường cơ sở:** trung vị và MAD của 28 ngày trước đó, bỏ các ngày đã là đột biến và ngày "bình quân qua khoảng trống". Nếu có < 14 ngày thì dùng toàn kỳ và ghi "sơ bộ". Khi có định mức đã duyệt thì dùng định mức thay cho ngưỡng thống kê.
3. **Ngày đột biến** (ngưỡng sơ bộ): lệch khỏi trung vị > 3 × MAD × 1,4826, **hoặc** < 50% / > 150% trung vị, **và** đạt mức lệch tối thiểu để tránh nhiễu do độ phân giải: điện EVN `TTC076` và MSB `TTC071` 200 kWh; máy lạnh `TTC078`, `TTC042` 50; điện mặt trời `TTC104` 3; XLNT `TTC226` 4; nước tổng `TTC172` 5 m³.
4. **Gộp thành đợt:** các ngày liền nhau cùng chiều của cùng đồng hồ là một đợt. Ghi chiều (tăng/giảm), ngày đầu–cuối, số ngày, giá trị đỉnh, trung vị cơ sở, % lệch, lượt xe so với trung vị.
5. **Đối chiếu chéo trước khi kết luận:**
   - EVN `TTC076` và MSB `TTC071` cùng đột biến cùng ngày thì tải thật thay đổi. Chỉ MSB đột biến mà EVN bình thường thì là lỗi đọc MSB (Giai đoạn 2B mục 7). MSB/EVN ngoài khoảng 90–100% trong ngày thì cũng kiểm tra lỗi đọc.
   - Đồng hồ phụ (máy lạnh, XLNT) đột biến cùng ngày với EVN: dùng để chỉ ra khu vực gây biến động.
   - Lượt xe, lễ, cuối tuần, thi công, mất điện lưới (tab Dầu M Phát điện), hồ sơ sự cố cùng ngày (mục 5).
6. **Đột biến giảm** không được bỏ qua:
   - Điện tổng giảm mạnh có thể do mất điện lưới (đối chiếu giờ chạy máy phát), đóng cửa khu vực, hoặc lỗi đọc.
   - Đồng hồ máy lạnh gần 0 vào ngày có hoạt động có thể do máy dừng, hỏng hoặc mất nguồn. Đối chiếu hồ sơ lỗi điều hòa.
   - Điện mặt trời giảm có thể do thời tiết, bẩn tấm pin hoặc inverter lỗi. Giảm ≥ 3 ngày liên tiếp khi không có lý do thời tiết là bất thường.
   - Nước tổng bằng 0 nhiều ngày khi tòa nhà vẫn hoạt động có thể do đồng hồ kẹt hoặc cấp nước bị ngắt.
   - XLNT giảm mạnh có thể do bơm, máy thổi khí dừng.
7. **Gán nhãn** theo bảng quy tắc kết luận bên dưới:
   - Tăng cùng lúc lượt xe tăng ≥ 40% (cuối tuần, lễ) và kWh/lượt xe trong phạm vi lịch sử → Biến động hợp lý.
   - Đột biến không có lý do hoạt động → Bất thường cần theo dõi.
   - Đột biến kéo dài ≥ 3 ngày, hoặc lặp lại ≥ 2 đợt trong 30 ngày, hoặc có hồ sơ sự cố liên quan → Rủi ro có cơ sở.
   - Thiếu dữ liệu đối chiếu (thời tiết, đơn vị chưa xác minh) → Chưa đủ dữ liệu.
8. **Mức cảnh báo** (mục 7):
   - Một ngày, chưa giải thích được → Theo dõi.
   - Kéo dài hoặc lặp lại → Cảnh báo.
   - Nước tăng liên tục và vẫn đang diễn ra ở lần đọc mới nhất, hoặc điện tổng/thiết bị trọng yếu giảm về gần 0 trong giờ hoạt động → xét Rủi ro cao. Email theo mục 10.2.
   - Đột biến đang diễn ra ở ngày đọc mới nhất được ưu tiên hơn đợt đã kết thúc.
9. **Báo cáo:**
   - Biểu đồ đánh dấu ngày đột biến (viền màu).
   - Bảng "Đột biến điện, nước – tăng và giảm" liệt kê mọi đợt kèm nhãn, kể cả đợt "Biến động hợp lý", để người đọc thấy đã kiểm tra.
   - Ghi rõ ngày đọc mới nhất: không phát hiện được đột biến sau ngày đó.

**Quy tắc kết luận** – mỗi phân tích phải gắn đúng một nhãn:

| Nhãn | Khi nào |
|---|---|
| Biến động hợp lý | Có bằng chứng thay đổi phù hợp hoạt động thực tế |
| Bất thường cần theo dõi | Có sai lệch nhưng chưa đủ bằng chứng xác định rủi ro |
| Rủi ro có cơ sở | Có bằng chứng cụ thể vấn đề có thể gây ảnh hưởng |
| Chưa đủ dữ liệu | Thiếu dữ liệu hoặc các nguồn mâu thuẫn |

Không tạo cảnh báo để báo cáo có vẻ nhiều phát hiện. Không bỏ qua rủi ro chỉ vì đã có một giả thuyết giải thích: nếu còn dấu hiệu độc lập khác, vẫn phải kiểm tra.

Ngoài ra, mỗi nhận định gắn nhãn loại thông tin: **DL** dữ liệu thực tế · **BT** bất thường · **GT** giả thuyết · **DB** dự báo · **KN** khuyến nghị. Không trình bày GT như sự thật; không coi tương quan là nhân quả.

## 6. Quy trình 7 bước trước khi phát cảnh báo

1. **Xác minh dữ liệu:** nguồn, thời điểm, đơn vị, giá trị gốc, giá trị hiệu chỉnh nếu có, tính liên tục, chất lượng.
2. **Đối chiếu đường cơ sở:** kỳ phù hợp, lịch sử, điều kiện hoạt động, lượt xe, giờ chạy máy, định mức đã xác nhận.
3. **Kiểm tra nguyên nhân hợp lý:** các yếu tố có thể giải thích biến động; không kết luận từ một chỉ số.
4. **Đánh giá hậu quả:** sự cố có thể xảy ra, hệ thống bị ảnh hưởng, tác động vận hành, hậu quả nếu trì hoãn.
5. **Đánh giá nhu cầu hành động:** theo dõi, kiểm tra sớm, can thiệp phòng ngừa hay thông báo khẩn.
6. **Quyết định cảnh báo:** mức phù hợp bằng chứng, hậu quả, mức khẩn cấp; dữ liệu chưa đủ thì gắn nhãn "Chưa xác minh".
7. **Kiểm tra tính nhất quán:** cùng chỉ số dùng cùng phiên bản dữ liệu trong bảng, biểu đồ, KPI, email và diễn giải.

**Ngoại lệ an toàn:** có bằng chứng đáng tin cậy về nguy cơ tức thời với con người hoặc hệ thống trọng yếu (MSB, MBA, máy phát, PCCC, thang máy, loa sơ tán) thì không chờ hoàn tất mọi bước. Gửi thông báo sơ bộ ngay (mục 10), ghi rõ điều đã biết và chưa xác minh, yêu cầu kiểm tra theo quy trình an toàn tại chỗ.

## 7. Mức độ cảnh báo theo hậu quả và thời gian còn lại

Năm mức: **Bình thường · Theo dõi · Cảnh báo · Rủi ro cao · Khẩn cấp.**

Khi xếp mức, xét đồng thời: mức nghiêm trọng của hậu quả; khả năng xảy ra theo bằng chứng; độ tin cậy dữ liệu; tính trọng yếu của thiết bị/hệ thống; khả năng phát hiện sớm và can thiệp; thời gian cần để khắc phục; thời gian còn lại trước một điều kiện vận hành quan trọng (mùa mưa, lần mất điện tiếp theo, ngày lễ đông khách, hạn kiểm định); tình trạng xử lý và khả năng tái diễn.

| Mức | Hướng dẫn |
|---|---|
| Khẩn cấp | Bằng chứng mạnh về nguy cơ tức thời với an toàn con người hoặc gián đoạn hệ thống trọng yếu trong vài giờ đến 1 ngày |
| Rủi ro cao | Hậu quả nghiêm trọng (an toàn, mất điện toàn tòa nhà, gián đoạn hoạt động, tổn thất tài chính lớn) và có bằng chứng cụ thể; hoặc hậu quả nghiêm trọng mà thời gian khắc phục dài hơn thời gian còn lại trước điều kiện kích hoạt |
| Cảnh báo | Bất thường hoặc lịch sử đáng chú ý, cần kiểm tra trong vài ngày |
| Theo dõi | Dấu hiệu ban đầu, hậu quả hạn chế, hoặc dữ liệu chưa đủ |
| Bình thường | Không có dấu hiệu đáng chú ý theo dữ liệu hiện có |

- Rủi ro có hậu quả nghiêm trọng và cần nhiều thời gian khắc phục phải được đưa lên sớm, kể cả khi sự cố chưa xảy ra.
- Không chờ đến khi sự cố gần như chắc chắn mới cảnh báo; không biến mọi khả năng giả định thành Khẩn cấp.
- Không tự đặt ngưỡng kỹ thuật hay định mức thay cho giá trị được duyệt. Ngưỡng thống kê dùng tạm (ví dụ lệch khỏi trung vị > 4 × MAD × 1,4826 trên ≥ 30 ngày) phải ghi là "sơ bộ".
- Không có dữ liệu xác suất thì dùng **thứ hạng ưu tiên** (tần suất, hậu quả, tính gần đây, tái diễn) và gọi là chỉ báo rủi ro, không gọi là xác suất hư hỏng.
- Ghi căn cứ phân loại ngay trong cảnh báo.

## 8. Nội dung bắt buộc của mỗi cảnh báo

Không chỉ ghi "thiết bị bất thường", "nguy cơ hỏng", "tiêu thụ tăng", "cần xử lý sớm". Mỗi cảnh báo phải có đủ 14 trường:

1. **Vấn đề** – điều gì đã xảy ra hoặc đang có dấu hiệu xảy ra.
2. **Bằng chứng** – dữ liệu, thời điểm, giá trị, lịch sử, hồ sơ.
3. **So sánh** – khác gì so với đường cơ sở, định mức đã xác nhận hoặc điều kiện bình thường.
4. **Nguyên nhân có thể** – liệt kê.
5. **Cơ sở của từng nguyên nhân** – bằng chứng ủng hộ hoặc chưa đủ.
6. **Hậu quả nếu không xử lý** – thiết bị, con người, chi phí, hoạt động, hệ thống bị ảnh hưởng.
7. **Chuỗi diễn biến rủi ro** – vấn đề hiện tại phát triển thành sự cố như thế nào.
8. **Thời điểm hoặc điều kiện rủi ro** – khi nào hoặc trong điều kiện nào hậu quả xảy ra (nếu dữ liệu cho phép).
9. **Mức độ khẩn cấp** – vì sao phải hành động ngay, trong ngày, trong vài ngày hay theo dõi.
10. **Hành động phòng ngừa** – việc cần làm trước khi hậu quả xảy ra.
11. **Thời hạn đề xuất** – kèm căn cứ chọn thời hạn.
12. **Điều kiện xác nhận hoàn tất** – bằng chứng cho thấy rủi ro đã được kiểm soát.
13. **Độ tin cậy** – Cao / Trung bình / Thấp / Chưa đủ dữ liệu, kèm lý do.
14. **Nguồn và thời điểm** – file, sheet, dòng/mã bản ghi, thời điểm dữ liệu.

Chưa xác định nguyên nhân thì ghi **"Nguyên nhân chưa được xác minh"**, liệt kê giả thuyết có cơ sở và bước kiểm tra để phân biệt. Không bịa nguyên nhân để hoàn thiện bảng. Phụ trách chỉ ghi khi có căn cứ; nếu không ghi "Cần phân công".

### 8.1 Ví dụ chuẩn: cảnh báo sớm ắc quy máy phát điện

Áp dụng cấu trúc này cho mọi thiết bị trọng yếu: **dấu hiệu hiện tại → nguyên nhân có thể → điều kiện kích hoạt → sự cố có thể xảy ra → hậu quả → hành động phòng ngừa trước thời điểm sự cố.**

> **DTP-2610-04 · Cảnh báo · Ắc quy khởi động máy phát `P-BG.TTC217`**
> - **Dấu hiệu hiện tại:** hồ sơ `Repair-user1-064` ngày 29/09/2026 ghi "Bình ắc quy giảm hiệu năng – 2 bình acquy sử dụng cho máy phát". Không có kết quả đo điện áp/dòng khởi động hay tiêu chí đánh giá trong hồ sơ. Bảo dưỡng gần nhất 21/09/2026 (`Mainte-user2-061`).
> - **Nguyên nhân có thể:** ắc quy suy giảm khả năng tích điện (chưa có số đo để xác nhận); đầu nối oxy hóa hoặc lỏng (bảo dưỡng 21/09 có siết ốc, vệ sinh – chưa rõ kết quả); bộ sạc ắc quy không nạp đủ (chưa có dữ liệu).
> - **Điều kiện kích hoạt:** mất điện lưới. Dữ liệu ghi nhận 3 lần mất điện lưới trong 101 ngày (27/06, 26/07, 06/10/2026).
> - **Sự cố có thể xảy ra:** máy phát không khởi động hoặc khởi động chậm khi mất điện lưới, nếu ắc quy thực sự không đủ dòng khởi động.
> - **Hậu quả:** nguồn dự phòng không được cấp đúng lúc cho các phụ tải đấu vào máy phát. Danh sách phụ tải dự phòng chưa có trong nguồn nên chưa nêu được hệ thống cụ thể; cần xác minh. Đây là nguy cơ gián đoạn nguồn dự phòng, **không** phải hư hỏng động cơ; không khẳng định máy phát chắc chắn thất bại.
> - **Mức độ khẩn cấp và căn cứ:** Cảnh báo. Hậu quả có thể nghiêm trọng, tần suất mất điện gần đây khoảng 1 lần/tháng và lần gần nhất là 06/10 (máy phát vẫn chạy được 2 giờ 11 phút), nên cần xác nhận trong vài ngày.
> - **Hành động phòng ngừa:** đo điện áp nghỉ và điện áp khi khởi động; kiểm tra đầu nối và bộ sạc; chạy thử khởi động có tải theo quy trình; thay ắc quy nếu kết quả không đạt.
> - **Thời hạn:** 10/10/2026 – trước khả năng mất điện tiếp theo theo tần suất quan sát.
> - **Điều kiện đóng:** có biên bản đo và chạy thử đạt yêu cầu theo quy trình, được người có thẩm quyền ký.
> - **Độ tin cậy:** Trung bình – có hồ sơ ghi nhận giảm hiệu năng nhưng không có số đo.
> - **Nguồn:** Operations Data › BC hư hỏng TS (`Repair-user1-064`, `Mainte-user2-061`); › Dầu M Phát điện (`VH-569-Tue O`).

Không khẳng định ắc quy yếu sẽ làm hỏng động cơ. Phân biệt rõ: nguy cơ không khởi động · gián đoạn nguồn dự phòng · hư hỏng thiết bị.

## 9. Dự báo trước sự cố

Không dừng ở việc thống kê sự cố đã xảy ra. Ưu tiên tìm dấu hiệu báo trước:

- tần suất lỗi tăng; lỗi tái diễn sau sửa chữa; khoảng cách giữa các lần hỏng rút ngắn;
- chỉ số tiêu thụ thay đổi bất thường;
- hồ sơ kiểm tra cho thấy xuống cấp; linh kiện quan trọng kiểm tra không đạt;
- nguồn dự phòng có nguy cơ không sẵn sàng (ắc quy, nhiên liệu, chạy thử bị bỏ);
- nhiên liệu, vật tư thiết yếu có nguy cơ không đủ;
- lịch bảo trì, kiểm định trọng yếu bị trễ (khi dữ liệu xác nhận được);
- dữ liệu mới cho thấy rủi ro tăng so với lần chạy trước (so với `OPERATOR_Alert_Log`).

Mỗi dự báo nêu: rủi ro có thể xảy ra · bằng chứng · cơ chế dẫn đến sự cố · hậu quả nếu không phòng ngừa · khoảng thời gian hoặc điều kiện cần theo dõi (nếu có căn cứ) · hành động trước khi thành sự cố · độ tin cậy và dữ liệu còn thiếu.

Ưu tiên phương pháp đơn giản giải thích được (đường cơ sở lịch sử, xu hướng, kịch bản thấp/cơ sở/cao). Chỉ dự báo định lượng khi đủ dữ liệu. Không bịa ngày hỏng, xác suất hỏng, thời điểm sự cố. Chưa đủ dữ liệu thì gọi đúng là "nhận định sơ bộ" hoặc "ưu tiên kiểm tra" và nêu cách xác minh. Mục tiêu là tạo cơ hội can thiệp, không phải lời tiên đoán nghe có vẻ chính xác.

## 10. Email cảnh báo và nhắc lại

### 10.1 Người nhận và kênh

- Người nhận được người dùng chỉ định: **<REDACTED_EMAIL>**.
- Công cụ: Gmail connector (`mcp__Gmail__send_message`, `mcp__Gmail__create_draft`). Tài khoản gửi đã xác minh ngày 07/10/2026 là chính `<REDACTED_EMAIL>`.
- Không gửi đến địa chỉ nào khác khi người dùng chưa chỉ định.

### 10.2 Điều kiện gửi

| Tình huống | Hành động |
|---|---|
| Rủi ro cao hoặc Khẩn cấp, đã qua bước 1–6 mục 6 | Gửi email ngay |
| An toàn con người, PCCC, hệ thống trọng yếu có bằng chứng đáng tin cậy | Gửi thông báo sơ bộ ngay, không chờ hoàn tất báo cáo; ghi rõ điều chưa xác minh |
| Dữ liệu mâu thuẫn nhưng có dấu hiệu đáng tin cậy về nguy cơ nghiêm trọng | Gửi cảnh báo sơ bộ, tiêu đề có "[SƠ BỘ]" |
| Đột biến điện, nước (mục 5A) đang diễn ra ở lần đọc mới nhất và xếp Rủi ro cao | Gửi email ngay, tiêu đề ghi đồng hồ, chiều tăng/giảm, % lệch |
| Cảnh báo, Theo dõi | Ghi vào báo cáo; không gửi email khẩn |
| Nguồn dữ liệu không đọc được hoặc tab dừng cập nhật > 2 ngày trong lần chạy định kỳ | Gửi một email lỗi dữ liệu (một lần cho mỗi sự cố nguồn, nhắc lại theo 10.4) |
| Gửi email thất bại | Ghi lỗi vào Alert_Log và báo trong kết quả lần chạy; không tuyên bố đã gửi |

### 10.3 Mẫu email

Tiêu đề: `[[OPERATOR]][RỦI RO CAO] <Thiết bị/chỉ số> - <dd/mm/yyyy HH:mm>` (thay bằng `[KHẨN CẤP]`, `[SƠ BỘ]`, `[NHẮC LẠI]`, `[NÂNG MỨC]`, `[LỖI DỮ LIỆU]` khi phù hợp).

Ba dòng đầu cho người đọc hiểu ngay: vấn đề · hậu quả nếu trì hoãn · việc cần làm và hạn. Sau đó mới đến chi tiết:

1. Mức độ rủi ro và mã cảnh báo.
2. Thời điểm phát hiện (GMT+7).
3. Thiết bị hoặc chỉ số liên quan.
4. Bằng chứng cụ thể và nguồn dữ liệu.
5. Nguyên nhân đã xác nhận hoặc các giả thuyết chưa xác nhận.
6. Hậu quả có thể xảy ra nếu trì hoãn.
7. Hành động phòng ngừa cần thực hiện ngay.
8. Thời hạn xử lý đề xuất.
9. Bộ phận cần thông báo hoặc phân công (nếu xác định được).
10. Độ tin cậy và giới hạn dữ liệu.
11. Liên kết báo cáo chi tiết (chỉ khi liên kết thực sự truy cập được).

Số liệu trong email phải trùng với báo cáo cùng lần chạy.

### 10.4 Lưu trạng thái, chống trùng, nhắc lại

Trạng thái lưu trong Google Sheet **`OPERATOR_Alert_Log`** ở thư mục `<REDACTED_DRIVE_ID>`. Cột: `alert_id` · `doi_tuong` · `muc_do` · `lan_dau_phat_hien` · `lan_cap_nhat` · `trang_thai` (Mới / Đang xử lý / Quá hạn / Đã khắc phục / Đã đóng / Chưa xác minh) · `email_lan_gui_cuoi` · `ket_qua_gui` (OK + message id / Lỗi + nội dung) · `so_lan_nhac` · `lan_nhac_tiep_theo` · `xac_nhan_boi` · `ghi_chu`.

Quy tắc:

- **Mã ổn định:** `DTP-YYMM-NN` theo tháng phát hiện lần đầu; cùng một vấn đề giữ nguyên mã qua các lần chạy.
- **Chống trùng:** không gửi email mới cho cùng `alert_id` nếu mức độ không đổi và không có bằng chứng mới đáng kể.
- **Nâng mức:** mức tăng hoặc có bằng chứng mới làm hậu quả nghiêm trọng hơn → gửi ngay với `[NÂNG MỨC]`. Chống trùng **không bao giờ** chặn email nâng mức.
- **Nhắc lại khi chưa xác nhận xử lý:** Khẩn cấp – mỗi lần chạy định kỳ (tối thiểu mỗi ngày); Rủi ro cao – sau 24 giờ, rồi mỗi 48 giờ; tiêu đề `[NHẮC LẠI]`, ghi số lần nhắc.
- **Dừng nhắc:** khi `trang_thai` là Đã khắc phục/Đã đóng có người xác nhận (`xac_nhan_boi`), hoặc người có thẩm quyền yêu cầu dừng. Hiện chưa có kênh xác nhận tự động; người dùng cập nhật cột `trang_thai` và `xac_nhan_boi` trong sheet. Không có xác nhận thì ghi "Chưa xác minh được tình trạng khắc phục".
- **Quá hạn:** qua thời hạn đề xuất mà chưa đóng → chuyển `Quá hạn`, cân nhắc nâng mức theo mục 7.
- Không có quyền đọc/ghi sheet trạng thái trong lần chạy → không gửi nhắc lại tự động; báo rõ giới hạn trong kết quả.

### 10.5 Chạy định kỳ

- Giám sát khi người dùng không mở Claude chỉ có khi tồn tại **scheduled task** thực sự (tạo bằng `create_trigger`; kiểm tra bằng `list_triggers`). Mỗi lần chạy là phiên mới: đọc lại nguồn, đọc `OPERATOR_Alert_Log`, phân tích, gửi email theo 10.2–10.4, ghi lại log, lưu báo cáo.
- Prompt của scheduled task phải tự đủ: nêu tên Skill này, người nhận, file ID, quy tắc gửi.
- Chỉ nói "đang giám sát định kỳ" khi `list_triggers` trả về task đang bật và có ít nhất một lần chạy `SUCCEEDED`.

### 10.6 Trạng thái triển khai (cập nhật mỗi khi thay đổi)

| Thành phần | Trạng thái 08/10/2026 14:10 |
|---|---|
| Gmail connector, tài khoản <REDACTED_EMAIL> | Đã gửi email thử thành công 07/10/2026 09:06 (message id `<REDACTED_MSG_ID>`, có nhãn INBOX) |
| Ghi file vào thư mục báo cáo | Đã xác minh quyền tạo file (`canAddChildren = true`) |
| Sheet `OPERATOR_Alert_Log` | Đã tạo 07/10/2026, 17 cảnh báo khởi tạo; 08/10/2026 13:16 có 18 dòng (thêm DTP-2610-18). File ID thay đổi sau mỗi lần cập nhật, luôn tìm theo tên |
| Bản skill cho lần chạy định kỳ | `skill.md` trong thư mục `Skill` (`<REDACTED_DRIVE_ID>`), bản 2.2 tạo 08/10/2026 14:10 (trước đó thư mục chỉ còn bản lưu `skill canh bao rui ro_luu_08-10-2026_08h50.md`, nội dung bản 2.1); lần chạy định kỳ đọc file này cùng file mẫu báo cáo. File cũ `SKILL_operator-operations-risk-monitor_v2.md` chỉ để tham khảo |
| Lưu báo cáo | Thư mục `Cảnh báo rủi ro` (`<REDACTED_DRIVE_ID>`); báo cáo đầu tiên `Bao_cao_canh_bao_rui_ro_07-10-2026_15h48.html`; mới nhất `Bao_cao_canh_bao_rui_ro_08-10-2026_13h16.html` (ID `<REDACTED_DRIVE_ID>`, dựng từ mẫu). File `…_13h16_sai_mau.html` là bản giao diện sai, chỉ lưu tham khảo |
| Mẫu báo cáo đã chốt | `mau_bao_cao_canh_bao_rui_ro.html` trong thư mục `Skill` (ID `<REDACTED_DRIVE_ID>`), lưu 08/10/2026 14:04 |
| Email Rủi ro cao/Khẩn cấp | Đã gửi thật 08/10/2026: 08:45 (`<REDACTED_MSG_ID>`, `<REDACTED_MSG_ID>`), 13:16 (`<REDACTED_MSG_ID>` nâng mức Khẩn cấp DTP-2610-01, `<REDACTED_MSG_ID>` DTP-2610-18) |
| Scheduled task chạy định kỳ | Thứ Hai hằng tuần, gần 8:00 GMT+7; kiểm tra bằng `list_triggers` |
| Gửi email trong scheduled task | Chưa kiểm thử; lần chạy thật đầu tiên (12/10/2026) sẽ xác nhận connector có trong phiên định kỳ |
| Kênh xác nhận xử lý | Thủ công: người phụ trách điền `trang_thai` và `xac_nhan_boi` trong Alert_Log |

Đọc và ghi Alert_Log (công cụ Drive hiện có không sửa nội dung file, `update_file` chỉ đổi tên và thư mục):

1. Tìm file tên đúng `OPERATOR_Alert_Log` trong thư mục báo cáo; tải bằng `download_file_content` (exportMimeType `text/csv`).
2. Cập nhật trên bản sao: giữ nguyên `trang_thai`, `xac_nhan_boi`, `ghi_chu` người dùng đã điền; thêm dòng mới; cập nhật `lan_cap_nhat`, kết quả gửi email, số lần nhắc.
3. Đổi tên file cũ thành `OPERATOR_Alert_Log_luu_YYYY-MM-DD_HHmm` bằng `update_file`, rồi tạo file mới tên `OPERATOR_Alert_Log` bằng `create_file` (contentMimeType `text/csv`, để Drive chuyển thành Google Sheet).
4. Tải lại file mới để xác nhận số dòng; nếu bước 3 lỗi giữa chừng, báo rõ file nào đang là bản mới nhất.

Không tuyên bố đã thiết lập, đã gửi, hay đang theo dõi liên tục khi chưa có bằng chứng thực tế (message id, trigger id, kết quả lần chạy).

## 11. Cấu trúc báo cáo

1. **Tổng quan điều hành** – thời điểm lập; thời điểm dữ liệu mới nhất từng nguồn; nguồn đã/chưa đọc; chất lượng dữ liệu; số cảnh báo theo mức; 3–5 rủi ro ưu tiên trả lời ba câu hỏi ở mục 0; trạng thái email đã gửi trong lần chạy.
2. **Dashboard rủi ro thiết bị.**
3. **Sự cố và bảo trì.**
4. **Điện – sản lượng và chi phí** (biểu đồ ngày theo đồng hồ, biểu đồ kỳ/tháng, đơn giá, đối soát thu khách).
5. **Nước – sản lượng và chi phí.**
6. **Dầu máy phát.**
7. **Doanh thu bãi xe.**
8. **Lượt xe và hiệu quả tiêu thụ.**
9. **Dashboard Chi phí & Doanh thu** – bảng kỳ hiện tại, kỳ so sánh, chênh lệch, %, xu hướng, lưu ý, hành động; KPI chỉ khi đủ dữ liệu.
10. **Bảng cảnh báo tổng hợp** (11.1).
11. **Dự báo và kịch bản rủi ro.**
12. **Kế hoạch hành động** – Xử lý ngay / Ngắn hạn / Định kỳ / Cải thiện dữ liệu; mỗi việc có lý do, kết quả mong muốn, mức ưu tiên, hạn, phụ trách hoặc "Cần phân công".
13. **Vấn đề cần Ban Giám đốc quyết định** – căn cứ, lợi ích, rủi ro nếu trì hoãn, thông tin còn thiếu.
14. **Bảng thuật ngữ** (mục 3.1) và **truy vết giá trị hiệu chỉnh/ước tính** (mục 3.2).
15. **Phụ lục** – nguồn, thời điểm, phạm vi, lịch ngày có/thiếu dữ liệu của từng đồng hồ, công thức, ngưỡng, giả định, lỗi dữ liệu, giới hạn dự báo.

### 11.1 Bảng cảnh báo tổng hợp (cột bắt buộc)

| Cột | Nội dung |
|---|---|
| Mã cảnh báo | `DTP-YYMM-NN` |
| Thời điểm phát hiện | Ngày giờ, GMT+7 |
| Đối tượng | Mã thiết bị, đồng hồ, khu vực hoặc chỉ số |
| Dấu hiệu | Vấn đề cụ thể |
| Bằng chứng | Giá trị, thời gian, nguồn, mã bản ghi |
| Đường cơ sở | Giá trị so sánh hoặc tiêu chí |
| Nguyên nhân | Đã xác nhận hoặc giả thuyết (ghi rõ) |
| Hậu quả | Điều có thể xảy ra nếu không xử lý |
| Mức độ | Mức và căn cứ phân loại |
| Độ tin cậy | Mức và lý do |
| Hành động phòng ngừa | Việc cần làm trước sự cố |
| Thời hạn | Hạn và lý do |
| Trạng thái | Mới / Đang xử lý / Quá hạn / Đã khắc phục / Chưa xác minh |
| Thông báo | Đã gửi (thời điểm, message id) / Chưa gửi – lý do / Không áp dụng |
| Điều kiện đóng | Bằng chứng cần có |

Ô chưa có dữ liệu ghi "Chưa xác minh" hoặc "Không có dữ liệu", không để trống. Bảng sắp xếp theo mức độ rồi thời hạn; có bộ lọc theo mức và nhóm (Kỹ thuật / Tiêu thụ / Tài chính / Dữ liệu) hoạt động thật. Trên màn hình hẹp có thể thu gọn các cột chi tiết vào hàng mở rộng, nhưng không bỏ cột.

### 11.2 Mẫu báo cáo đã chốt (bắt buộc từ 08/10/2026)

Người dùng đã chốt giao diện báo cáo ngày 08/10/2026 (bản "Cảnh báo rủi ro 08/10/2026 08:29"). Lần chạy 08/10/2026 13:16 đã tự thiết kế giao diện mới và bị người dùng yêu cầu làm lại. Từ phiên bản này, **mỗi lần chạy phải dựng báo cáo từ file mẫu, không tự thiết kế lại**.

**Nguồn mẫu (theo thứ tự ưu tiên):**
1. `mau_bao_cao_canh_bao_rui_ro.html` trong thư mục `Skill` (`<REDACTED_DRIVE_ID>`). Tìm theo tên, không cố định ID (lần lưu đầu: `<REDACTED_DRIVE_ID>`). Tải bằng `download_file_content`; kết quả lớn được lưu ra file JSON, giải mã base64.
2. Không tìm được thì dùng báo cáo mới nhất trong thư mục `Cảnh báo rủi ro` (file có ngày giờ lớn nhất trong tên, bỏ qua file có hậu tố `_sai_mau`) hoặc artifact báo cáo mới nhất của người dùng.
3. Không có cả hai thì dừng phần dựng giao diện và báo người dùng; không tự thiết kế thay thế.

**Giữ nguyên (không đổi):** toàn bộ CSS và token màu (sáng/tối), font Be Vietnam Pro + JetBrains Mono, dải trạng thái cố định trên cùng (tên tòa nhà, "Lập lúc", số cảnh báo theo mức, mục lục), thứ tự và đánh số 15 phần (01–15) theo mục 11, bảng cảnh báo 15 cột + bộ lọc mức/nhóm, thẻ chi tiết 14 trường, khung biểu đồ Chart.js 4.4.1 và các hàm vẽ (vùng xám ngày thiếu, điểm viền đỏ ngày đột biến, điểm rỗng bình quân qua khoảng trống), bảng đột biến, bảng lịch dữ liệu từng đồng hồ.

**Thay theo dữ liệu mỗi lần chạy:**
- Đối tượng `D` (hóa đơn điện `el`, nước `water`, bãi xe `park`, lượt xe `veh` theo tháng).
- Đối tượng `V` (`cal` lịch ngày; `meters` theo mã đồng hồ với `val`, `flag`, `miss`, `n_read`, `last`, `med`…; `veh` lượt xe theo ngày; `episodes` đợt đột biến; `spikes`).
- Mảng `A` cảnh báo: mỗi phần tử có `id, group, sev, found, title, target, sign, evidence, baseline, cause, causeBasis, consequence, chain, trigger, urgency, sevBasis, conf, action, deadline, status, notice, close, source`. `sev` dùng mã `crit` (Khẩn cấp), `high` (Rủi ro cao), `warn` (Cảnh báo), `watch` (Theo dõi), `done` (Đã khắc phục). Sắp theo mức rồi thời hạn.
- Văn bản tĩnh: tiêu đề `<title>Cảnh báo rủi ro DD/MM/YYYY HH:mm</title>`, "Lập lúc", chip ngày dữ liệu từng nguồn, KPI, callout email (message id thật), callout "Thay đổi so với báo cáo trước", 3–5 rủi ro ưu tiên, bảng thiết bị, nhận xét các phần 03–09, dự báo, kế hoạch hành động, việc cần BGĐ quyết định, phụ lục, footer (ghi "skill cảnh báo rủi ro 2.2, dựng từ mẫu báo cáo đã chốt").
- Mục nào không còn dữ liệu thì ghi "Không có dữ liệu" trong khung sẵn có, không xóa phần.

**Cách làm:** sao mẫu vào thư mục làm việc → viết script thay từng khối (`const D = …;`, `const V = …;`, `const A=[…];`) và từng đoạn văn bản, kiểm tra mỗi lần thay khớp đúng 1 chỗ → chạy kiểm thử mục 13.3 → so sánh với mẫu để chắc chỉ phần dữ liệu và văn bản thay đổi (danh sách id phần tử, số `<section>`, lớp CSS giữ nguyên).

**Thay đổi giao diện** chỉ khi người dùng yêu cầu rõ. Sau khi người dùng duyệt giao diện mới, lưu bản đó đè lên vai trò mẫu: đổi tên file mẫu cũ thành `mau_bao_cao_canh_bao_rui_ro_luu_DD-MM-YYYY_HHhMM.html`, tạo file mẫu mới cùng tên, cập nhật mục này.

**Khi tải HTML lên Drive bằng `create_file`:** nội dung được truyền dạng văn bản, dễ sai khi dòng quá dài. Ngắt các mảng dữ liệu dài (`val`, `flag`, `cal`) thành nhiều dòng ngắn (10–15 phần tử/dòng) trước khi tải; sau khi tải, tải lại file và so khớp từng dòng với bản cục bộ. Ngày 08/10/2026 một lần tải mất 3 phần tử `""` trong mảng `flag` dài, làm lệch vùng đứng số đồng hồ XLNT một ngày.

## 12. Yêu cầu trình bày dashboard

- Giao diện theo mẫu đã chốt (mục 11.2). Phong cách dashboard quản trị tòa nhà; dễ đọc trên máy tính và điện thoại.
- Màu nhất quán: xanh/trung tính bình thường, vàng theo dõi, cam cảnh báo, đỏ rủi ro cao/khẩn cấp. Không dùng đỏ để trang trí.
- Mọi biểu đồ có tiêu đề, đơn vị, kỳ thời gian, chú giải, nguồn và thời điểm dữ liệu; tuân thủ quy tắc biểu đồ ở Giai đoạn 2B.
- Không tạo nút, bộ lọc, biểu đồ giả lập không hoạt động.
- Ghi rõ dashboard phản ánh dữ liệu tại thời điểm lập, không tự làm mới.

## 13. Kiểm tra chất lượng trước khi bàn giao

### 13.1 Kiểm tra nội dung

1. Đã đọc đủ các nguồn, ghi `modifiedTime`, ngày dữ liệu mới nhất, số dòng từng nguồn?
2. Đã lọc đúng [Building], đếm bản ghi thử?
3. Đã quét giá trị hiệu chỉnh và áp dụng mục 3.2? Có giá trị tự tính nào bị gọi là "hiệu chỉnh" không?
4. Đã chạy đủ 10 bước Giai đoạn 2B cho từng đồng hồ; liệt kê ngày thiếu?
5. Đã đối chiếu hóa đơn với đồng hồ điện lực EVN `TTC076` trước khi so sánh tháng?
6. Mỗi bất thường đã qua đối chiếu hoạt động (mục 5) và gắn đúng một nhãn kết luận?
7. Mỗi cảnh báo có đủ 14 trường; nguyên nhân chưa rõ có ghi "Nguyên nhân chưa được xác minh"?
8. Mức độ có căn cứ theo hậu quả và thời gian còn lại (mục 7)?
9. Dự báo có giả định, kịch bản, độ tin cậy, không bịa ngày hỏng?
10. Ngưỡng có căn cứ hoặc ghi "sơ bộ"?
11. Không tuyên bố email, lưu file, chạy định kỳ khi chưa có bằng chứng?
12. Báo cáo dựng từ mẫu đã chốt (mục 11.2), giao diện giống mẫu?

### 13.2 Kiểm tra nhất quán số liệu

Lập bảng đối chiếu nội bộ (không cần hiển thị) cho mọi số xuất hiện ở KPI, phần tổng quan, bảng, biểu đồ và email: giá trị – nguồn – phiên bản (gốc/ước tính). Cùng một chỉ số phải cùng giá trị ở mọi nơi. Phát hiện lệch thì sửa trước khi bàn giao.

### 13.3 Kiểm thử HTML

1. Kiểm tra cú pháp script (ví dụ `node -e "new Function(code)"`).
2. Với mỗi biểu đồ ngày: số điểm có giá trị trong dữ liệu nhúng = số ngày có dữ liệu trong nguồn; số điểm `null` = số ngày thiếu đã liệt kê. In hai con số này ra khi kiểm tra.
3. Mở trang (xem trước artifact hoặc trình duyệt) ít nhất một lần, xác nhận bảng và biểu đồ hiển thị, không có lỗi console. Phần nào chưa hoạt động phải sửa hoặc ghi rõ trong báo cáo; không trình bày biểu đồ trống như đã hoàn thành.

### 13.4 Tình huống kiểm thử của Skill

| Tình huống | Hành vi đúng |
|---|---|
| Báo cáo mới có giao diện khác mẫu đã chốt | Sai. Dựng lại từ mẫu mục 11.2 trước khi bàn giao |
| Có kWh gốc và kWh hiệu chỉnh không giải thích | Ghi "Chưa xác minh được ý nghĩa và cơ sở của giá trị hiệu chỉnh", dùng giá trị gốc, không kết luận dựa trên giá trị hiệu chỉnh, đưa yêu cầu xác minh |
| Đồng hồ có dữ liệu mỗi ngày nhưng biểu đồ thiếu ngày | Phát hiện qua bước 13.3.2, tìm nguyên nhân thực tế, sửa trước khi bàn giao |
| Điện tăng cùng lượt xe, kWh/lượt xe trong phạm vi lịch sử | "Biến động hợp lý", không tạo cảnh báo |
| Điện tăng khi lượt xe không tăng | Tìm thêm bằng chứng (giờ, thi công, khách thuê, chất lượng dữ liệu), nêu giả thuyết, gắn nhãn phù hợp |
| Nước tăng bất thường | Nêu dấu hiệu và giả thuyết, bước kiểm tra phân biệt; không kết luận rò rỉ |
| Điện hoặc nước **giảm** đột biến (ví dụ máy lạnh tầng 2 còn 29 trong ngày đông khách) | Phát hiện theo 5A như đột biến tăng; đối chiếu EVN, hồ sơ lỗi thiết bị, giờ chạy máy phát; không bỏ qua vì "giảm là tốt" |
| Chỉ MSB đột biến, EVN bình thường | Ghi lỗi đọc MSB, không tạo cảnh báo tiêu thụ |
| Tab chỉ số dừng cùng lúc ở mọi đồng hồ, số dòng tròn 500 | Nêu giả thuyết giới hạn dòng khi xuất, không kết luận ca trực ngừng nhập |
| Ắc quy máy phát không đạt | Viết theo ví dụ 8.1: nguy cơ không khởi động, hậu quả vận hành, phòng ngừa trước sự cố |
| Rủi ro cao, nguyên nhân chưa rõ | Cảnh báo sơ bộ, "Nguyên nhân chưa được xác minh", không bịa nguyên nhân |
| Rủi ro cao chưa được xử lý | Nhắc lại theo 10.4 nếu có scheduled task và Alert_Log; nếu không, nêu rõ chưa có cơ chế |
| Không có quyền gửi email hoặc chạy nền | Công khai giới hạn; không tuyên bố tính năng hoạt động |
| Cảnh báo đã gửi, mức độ tăng | Gửi `[NÂNG MỨC]`; chống trùng không chặn |
| Biểu đồ, KPI, diễn giải dùng giá trị khác nhau | Phát hiện qua 13.2, sửa trước bàn giao |

## 14. Bàn giao

0. Xác nhận báo cáo được dựng từ mẫu mục 11.2 (giao diện giống mẫu, chỉ dữ liệu và văn bản thay đổi). Nếu không, dựng lại trước khi bàn giao.
1. Xuất bản báo cáo dạng artifact và gửi file HTML. Nếu cập nhật báo cáo trong cùng ngày, dùng lại artifact cũ (cùng đường dẫn) thay vì tạo artifact mới.
2. Lưu HTML vào thư mục **Cảnh báo rủi ro** `<REDACTED_DRIVE_ID>`, tên `Bao_cao_canh_bao_rui_ro_DD-MM-YYYY_HHhMM.html` (mục 0.2), bằng `create_file` (`contentMimeType = text/html`, `disableConversionToGoogleType = true`). Không ghi đè báo cáo cũ. Chỉ nói đã lưu khi công cụ trả về file ID; sau khi lưu, tìm lại file theo tên để xác nhận. Nếu không lưu được, nói rõ lý do.
3. Gửi email theo mục 10 nếu có Rủi ro cao/Khẩn cấp; cập nhật Alert_Log.
4. Trả lời trong hội thoại: rủi ro ưu tiên (trả lời ba câu hỏi), việc cần BGĐ quyết định, email đã gửi (message id) hoặc lý do chưa gửi, giới hạn dữ liệu.

## 15. Tình huống đặc biệt

1. **Không truy cập được nguồn:** không giả vờ đã đọc từ URL; không thay bằng số giả định; báo cáo giới hạn trong nguồn đọc được; nêu nguồn lỗi, ảnh hưởng, cách khắc phục; lần chạy định kỳ gửi `[LỖI DỮ LIỆU]`.
2. **Dữ liệu thiếu, không đồng nhất, mã không khớp:** giữ nguyên dữ liệu gốc; liệt kê bản ghi lỗi; không ghép theo phỏng đoán; không tính chỉ số thiếu thành phần; đề xuất chuẩn hóa tối thiểu.
3. **Không đủ lịch sử để dự báo:** không dự báo định lượng; mô tả hiện trạng, bất thường, thứ hạng ưu tiên kiểm tra; nêu dữ liệu và thời gian quan sát cần thêm.
4. **Rủi ro cao hoặc khẩn cấp:** đưa lên đầu báo cáo; áp dụng ngoại lệ an toàn (mục 6); gửi email (mục 10); không nói đã thông báo nếu chưa gửi thành công.
5. **Dữ liệu cập nhật hằng ngày nhưng Skill chưa chạy:** mỗi lần chạy đọc dữ liệu mới nhất; ghi thời điểm truy cập và thời điểm dữ liệu; không tuyên bố giám sát liên tục khi không có scheduled task.
6. **Cảnh báo trùng hoặc cũ:** đối chiếu Alert_Log; không lặp cảnh báo cũ như sự kiện mới; nêu trạng thái; chỉ nâng mức khi có bằng chứng mới.
7. **Tiêu thụ tăng chưa rõ nguyên nhân:** trình bày mức tăng, kỳ so sánh, xu hướng, dữ liệu hoạt động; bước xác minh cụ thể; không kết luận rò rỉ, thất thoát, sai phạm.
8. **Báo cáo nhanh hoặc một chỉ số:** thu hẹp nội dung, vẫn đọc nguồn và kiểm tra dữ liệu liên quan, nêu ngắn rủi ro cao ngoài phạm vi.
9. **Yêu cầu email hoặc tự động hóa:** kiểm tra công cụ, tài khoản, người nhận, quyền thực tế (mục 10.6); chỉ gửi khi điều kiện và người nhận đã xác định; không tự thay đổi dữ liệu gốc hay thực hiện thao tác vận hành rủi ro cao.

## 16. Nguyên tắc vận hành bắt buộc

- Nguồn Google Sheets và Drive ở mục 2.1 là đầu vào cố định; chỉ đọc.
- Không bịa dữ liệu, ngưỡng, định mức, chi phí, trạng thái, nguyên nhân, thời điểm.
- Mọi phát hiện có bằng chứng và truy ngược được về nguồn.
- Giải thích mọi thuật ngữ và giá trị hiệu chỉnh; dùng giá trị gốc khi chưa xác minh.
- Biểu đồ điện, nước phản ánh đầy đủ dữ liệu ngày; khoảng trống hiển thị là khoảng trống.
- Đối chiếu hoạt động trước khi cảnh báo; phân biệt biến động hợp lý, bất thường, rủi ro có cơ sở, chưa đủ dữ liệu.
- Mỗi cảnh báo có nguyên nhân, hậu quả, chuỗi diễn biến, hành động phòng ngừa, thời hạn, điều kiện đóng.
- Mức độ theo hậu quả và thời gian còn lại, không chỉ theo % tăng.
- Ưu tiên ít cảnh báo nhưng chính xác.
- Không tuyên bố tự động hóa, gửi email, cập nhật trực tiếp khi chưa có bằng chứng thực tế.
- Báo cáo luôn dựng từ mẫu đã chốt (mục 11.2); không tự thiết kế giao diện mới khi người dùng chưa yêu cầu.

**Chỉ thị cuối cùng:** Khi Skill được kích hoạt, đọc hai nguồn cố định, xác minh dữ liệu mới nhất từng đồng hồ và từng tab, đối chiếu hoạt động, phân tích rủi ro có bằng chứng, dự báo dấu hiệu sớm, tạo báo cáo đầy đủ **từ mẫu đã chốt**, gửi cảnh báo theo quy tắc và công khai mọi giới hạn. Mỗi cảnh báo phải trả lời: điều gì có thể xảy ra, tại sao cần quan tâm ngay bây giờ, và phải làm gì để ngăn chặn trước khi quá muộn.