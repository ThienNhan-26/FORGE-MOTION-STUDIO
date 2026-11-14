from core.coordinator import Coordinator

if __name__ == "__main__":
    forge = Coordinator()
    # Yêu cầu đạo diễn tạo video 2 cảnh
    request = "Tạo video 2 cảnh cho phim THE LAST LIGHT. Cảnh 1 màu đen, chữ THE LAST LIGHT. Cảnh 2 màu xanh, hạt bụi bay."
    forge.execute(request)