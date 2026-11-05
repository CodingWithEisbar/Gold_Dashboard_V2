# Công thức và đối chiếu

Đã đọc toàn bộ `GOLD_PREMIUM_AGENT_MASTER_PROMPT.md`. File `Gold_Premium_Infographic_Calculator.html` không có trong repository/thư mục Downloads được kiểm tra. Không thể tuyên bố đã đối chiếu với file đó. File được cung cấp thực tế là `GOLD_PREMIUM_ARCHITECTURE_INFOGRAPHIC.html`; đã kiểm tra công thức hiển thị và hàm JavaScript `calc()` trong file này.

HTML kiến trúc là minh họa: ask=140 triệu, bid=137 triệu, quantity=1, phí=0. Nó đổi triệu sang VND và nghìn phí sang VND, tính `pnl = bid*quantity - ask*quantity - fees`, return chia `ask*quantity`, **chưa cộng buy fees vào mẫu số**. Backend giữ đúng ca phí 0; tách phí mua/bán/lưu trữ/thuế và cộng phí mua vào vốn theo master prompt. Không lấy số demo làm quote production.

Hằng số Decimal chính xác: 1 lượng = 37.5g; 1 chỉ = 0.1 lượng; 1 troy ounce = 31.1034768g. `app/domain/gold_math.py` là nguồn tính toán duy nhất, version 1.0.0. Context tính chính xác 50 chữ số, không làm tròn bước trung gian; DB quote NUMERIC(24,8), API chuỗi Decimal; UI chỉ làm tròn tiền khi trình bày.

```text
world_reference = XAUUSD * USDVND * 37.5 / 31.1034768
premium_absolute = domestic_ask - world_reference
premium_pct = premium_absolute / world_reference * 100
spread = ask - bid
invested = quantity_luong * entry_ask + buy_fees
gross_sale = quantity_luong * exit_bid
net_proceeds = gross_sale - sell_fees - storage_fees - tax
net_pnl = net_proceeds - invested
return_pct = net_pnl / invested * 100
break_even_exit_bid = (invested + sell_fees + storage_fees + tax) / quantity_luong
future_world = world_now * (1 + world_change_pct / 100)
future_ask = future_world * (1 + future_premium_pct / 100)
future_bid = future_ask - future_spread
```

Mua là **ask của cửa hàng**, bán là **bid của cửa hàng**, cùng provider/product/region, đúng ngày. Không carry-forward. Có thể nhập manual_entry_ask mà không tạo quote giả. Ngày bán mặc định là business_date của snapshot mới nhất; nếu ngày đó không có daily reference hợp lệ thì trả missing, không lùi ngày trong im lặng. Fees/tax mặc định 0, không giả định thuế suất pháp lý.

Kịch bản luôn là `SCENARIO, NOT OBSERVED PRICE`, người dùng nhập world reference/ask/spread. Tỷ giá giữ nguyên trong world reference; thay đổi premium đối nghịch giá thế giới được xem qua các kịch bản độc lập, chưa có mô hình quy kết nhân quả/hồi quy. Không trình bày tác động spot và FX như một kết quả đã được tách chính xác.

Backtest sử dụng cùng entry ask và exit bid từng ngày có dữ liệu; biểu đồ tối đa 366 ngày cuối trong thời gian nắm giữ, ngày thiếu để null. Các phí giả định được trừ đầy đủ mỗi lần thanh lý lý thuyết. Không có nội suy.

Ca nghiệm thu cố định: 1 lượng, entry ask 140.000.000, exit bid 137.000.000, phí 0 → lỗ 3.000.000 VND, return −2.142857…%. Tests còn kiểm tra hòa vốn, phí trong mẫu số, chi/lượng, NaN/Infinity/float, số âm, ask<bid, missing spot/FX, và premium co hẹp làm P&L thấp hơn khi giữ biến khác.
