# test_blender.py
from storage.database import init_db
from core.task import Task, TaskType
from core.scheduler import TaskScheduler

if __name__ == "__main__":
    init_db()
    scheduler = TaskScheduler()
    
    # Test 2 & 3: Tạo scene Cube và Render
    task = Task(
        task_id="t_cube",
        title="Render Cube",
        description="""Viết script Blender để:
1. Xóa hết object mặc định.
2. Tạo 1 khối lập phương.
3. Tạo 1 Camera hướng vào khối lập phương.
4. Tạo 1 đèn Sun.
5. Set render engine là BLENDER_EEVEE.
6. Render và lưu file ảnh.""",
        task_type=TaskType.BLENDER_SCRIPT
    )
    
    scheduler.run_graph([task])