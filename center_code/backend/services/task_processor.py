"""
后台任务处理器
按需处理待处理的任务，定时任务使用轻量级定时检查
"""
import threading
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import VideoTask, ChatTask, ListenTask, PublishPlan, PlanVideo
from db import get_db
from services.task_executor import (
    execute_video_upload,
    execute_chat_send,
    execute_listen_start,
    execute_listen_stop
)

class TaskProcessor:
    """任务处理器（定时任务使用轻量级定时检查，其他任务按需触发）"""
    
    def __init__(self, poll_interval: int = None):
        """
        初始化任务处理器
        
        Args:
            poll_interval: 定时任务检查间隔（秒），默认 5 秒
        """
        self.poll_interval = poll_interval or 5  # 默认5秒检查一次
        self.is_running = False
        self.thread = None
    
    def start(self):
        """启动定时任务检查器（轻量级，只检查定时任务）"""
        if self.is_running:
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._schedule_check_loop, daemon=True)
        self.thread.start()
        print(f"定时任务检查器已启动，每 {self.poll_interval} 秒检查一次定时任务")
    
    def stop(self):
        """停止定时任务检查器"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _schedule_check_loop(self):
        """定时任务检查循环（轻量级，只检查定时任务）"""
        while self.is_running:
            try:
                self._check_scheduled_tasks()
            except Exception as e:
                print(f"[定时检查] 检查定时任务时出错: {e}")
                import traceback
                traceback.print_exc()
            
            time.sleep(self.poll_interval)
    
    def _check_scheduled_tasks(self):
        """检查并处理到期的定时任务（轻量级检查）"""
        with get_db() as db:
            now = datetime.now()
            
            # 1. 检查是否存在到点的计划视频（不再依赖计划时间）
            due_plan_video = db.query(PlanVideo.id).join(
                PublishPlan, PlanVideo.plan_id == PublishPlan.id
            ).filter(
                PublishPlan.status.in_(['pending', 'publishing']),
                PlanVideo.status == 'pending',
                or_(PlanVideo.publish_time.is_(None), PlanVideo.publish_time <= now)
            ).first()

            if due_plan_video:
                print("[定时检查] 检测到到点的计划视频，触发处理")
                # 触发完整处理（在后台线程中）
                def trigger_processing():
                    try:
                        self._process_pending_tasks()
                    except Exception as e:
                        print(f"[定时检查] 触发任务处理失败: {e}")
                
                thread = threading.Thread(target=trigger_processing, daemon=True)
                thread.start()
            
            # 2. 检查到期的 VideoTask 定时发布任务
            # 设计思路：一旦到达发布时间，就把这些任务当作“立即发布”来处理
            # 做法：将 publish_date 置为空，让它们走与立即发布相同的处理逻辑
            scheduled_tasks = db.query(VideoTask).filter(
                VideoTask.status == 'pending',
                VideoTask.publish_date <= now,
                VideoTask.publish_date.isnot(None)
            ).limit(10).all()  # 限制每次最多处理10个
            
            if scheduled_tasks:
                print(f"[定时检查] 发现 {len(scheduled_tasks)} 个到期的定时发布任务，转为立即发布并触发处理")
                
                # 将这些任务的 publish_date 清空，让它们与“立即发布”任务使用同一套逻辑
                for task in scheduled_tasks:
                    task.publish_date = None
                db.commit()
                
                # 触发完整处理（在后台线程中），内部会按“立即发布”逻辑处理这些任务
                def trigger_processing():
                    try:
                        self._process_pending_tasks()
                    except Exception as e:
                        print(f"[定时检查] 触发任务处理失败: {e}")
                
                thread = threading.Thread(target=trigger_processing, daemon=True)
                thread.start()
    
    def _process_video_tasks(self, db: Session):
        """处理立即发布的视频任务"""
        # 排除已完成的任务（status='completed'）和未到期的定时发布任务（publish_date 不为 None）
        # 只处理 pending、uploading 状态的任务（failed 任务由上层逻辑决定是否重置为 pending）
        video_tasks = db.query(VideoTask).filter(
            VideoTask.status != 'completed',  # 排除已完成的任务
            VideoTask.publish_date.is_(None)  # 排除定时发布任务（publish_date 不为 None 的）
        ).filter(
            VideoTask.status.in_(['pending', 'uploading'])
        ).order_by(VideoTask.created_at.asc()).limit(10).all()
        
        if video_tasks:
            print(f"[TASK POLL] 发现 {len(video_tasks)} 个待处理的视频任务（已排除已完成和定时发布任务）")
        
        for task in video_tasks:
            # 再次确认跳过已完成的任务（双重检查）
            if task.status == 'completed':
                print(f"[TASK POLL] 跳过已完成的任务 {task.id}")
                continue
            
            # 再次确认跳过定时发布任务（双重检查）
            if task.publish_date is not None:
                print(f"[TASK POLL] 跳过定时发布任务 {task.id} (发布时间: {task.publish_date})")
                continue
            
            # 检查任务是否已经在处理中（通过started_at判断）
            if task.status == 'uploading' and task.started_at:
                # 如果任务已经开始超过一定时间还没完成，可能是卡住了，重新处理
                elapsed_seconds = (datetime.now() - task.started_at).total_seconds()
                # 阈值从 10 分钟改为 3 分钟，加快卡死任务的自动恢复
                if elapsed_seconds < 180:  # 3分钟内，认为正在处理中
                    print(f"[TASK POLL] 任务 {task.id} 正在处理中（已运行 {int(elapsed_seconds)} 秒），跳过")
                    continue
                else:
                    # 任务可能卡住了，重置状态
                    print(f"[TASK POLL] ⚠️ 任务 {task.id} 可能卡住了（已运行 {int(elapsed_seconds)} 秒），重置为 pending 状态，准备重新发布")
                    task.status = 'pending'
                    task.started_at = None
                    task.error_message = None
                    db.commit()
            
            # 立即更新任务状态为 uploading，避免重复处理
            # 注意：这里需要刷新对象以确保获取最新状态
            db.refresh(task)
            if task.status != 'pending':
                print(f"[TASK POLL] 任务 {task.id} 当前状态为 {task.status}（非 pending），跳过（可能已被其他进程处理或已重置）")
                continue
            
            try:
                # 立即更新任务状态为 uploading，防止重复处理
                # 注意：不设置 started_at，让任务执行器来设置，避免时序问题
                task.status = 'uploading'
                task.progress = 0
                # 不设置 started_at，让 execute_video_upload 来设置
                db.commit()
                print(f"[TASK POLL] 任务 {task.id} 状态已更新为 uploading，准备启动")
                
                # 在后台线程中执行
                import asyncio
                thread = threading.Thread(
                    target=lambda tid=task.id: asyncio.run(execute_video_upload(tid)),
                    daemon=True
                )
                thread.start()
                print(f"[TASK POLL] ✓ 启动视频上传任务 {task.id}: {task.video_title} (状态: {task.status})")
            except Exception as e:
                print(f"[TASK POLL] ✗ 启动视频上传任务 {task.id} 失败: {e}")
                # 更新任务状态为失败
                try:
                    task.status = 'failed'
                    task.error_message = f"启动任务失败: {str(e)}"
                    db.commit()
                except:
                    pass
    
    def _process_pending_tasks(self):
        """处理待处理的任务"""
        with get_db() as db:
            now = datetime.now()
            
            publish_plans = db.query(PublishPlan).filter(
                PublishPlan.status == 'pending'
            ).all()
            
            if publish_plans:
                print(f"[TASK POLL] 发现 {len(publish_plans)} 个到期的发布计划")
                
                for plan in publish_plans:
                    try:
                        db.refresh(plan)
                        if plan.status != 'pending':
                            print(f"[TASK POLL] 发布计划 {plan.id} 状态已变更为 {plan.status}，跳过处理")
                            continue
                        
                        print(f"[TASK POLL] 处理发布计划: {plan.plan_name} (ID: {plan.id})")
                        
                        plan_videos = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'pending'
                        ).all()
                        
                        if not plan_videos:
                            print(f"[TASK POLL] 发布计划 {plan.id} 没有待发布的视频，标记为已完成")
                            plan.status = 'completed'
                            plan.updated_at = now
                            db.commit()
                            continue
                        
                        from models import Account
                        accounts = db.query(Account).filter(
                            Account.platform == plan.platform,
                            Account.login_status == 'logged_in'
                        ).all()
                        
                        if not accounts:
                            print(f"[TASK POLL] 发布计划 {plan.id} 的平台 {plan.platform} 没有已登录的账号，标记为失败")
                            for video in plan_videos:
                                video.status = 'failed'
                            plan.status = 'failed'
                            plan.failed_count = len(plan_videos)
                            plan.pending_count = 0
                            plan.updated_at = now
                            db.commit()
                            continue
                        
                        from pathlib import Path
                        import os
                        
                        for i, video in enumerate(plan_videos):
                            if video.publish_time and video.publish_time > now:
                                print(f"[TASK POLL] PlanVideo {video.id} 发布时间未到 ({video.publish_time})，跳过")
                                continue
                            
                            existing_task = db.query(VideoTask).filter(
                                VideoTask.plan_video_id == video.id
                            ).first()
                            
                            if existing_task:
                                print(f"[TASK POLL] PlanVideo {video.id} 已有任务 {existing_task.id}(status={existing_task.status})，跳过")
                                continue
                            
                            video_path = video.video_url
                            file_exists = False
                            
                            if video_path.startswith('http://') or video_path.startswith('https://'):
                                file_exists = True
                            else:
                                if video_path.startswith('file://'):
                                    video_path = video_path[7:]
                                elif video_path.startswith('/'):
                                    backend_dir = Path(__file__).parent.parent
                                    if video_path.startswith('/uploads/'):
                                        uploads_path = backend_dir.parent / 'uploads'
                                        full_path = uploads_path / video_path.lstrip('/uploads/')
                                        video_path = str(full_path)
                                    else:
                                        video_path = str(backend_dir / video_path.lstrip('/'))
                                file_exists = os.path.exists(video_path)
                            
                            if file_exists:
                                account = accounts[i % len(accounts)]
                                
                                video_task = VideoTask(
                                    account_id=account.id,
                                    device_id=account.device_id,
                                    video_url=video.video_url,
                                    video_title=video.video_title or f"视频 {i+1}",
                                    thumbnail_url=video.thumbnail_url,
                                    status='pending',
                                    plan_video_id=video.id
                                )
                                db.add(video_task)
                                db.flush()
                                video.status = 'processing'
                                print(f"[TASK POLL] 为 PlanVideo {video.id} 创建 VideoTask，账号: {account.account_name}")
                            else:
                                print(f"[TASK POLL] 视频文件不存在，标记为失败: {video.video_url}")
                                video.status = 'failed'
                        
                        published_count = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'published'
                        ).count()
                        processing_count = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'processing'
                        ).count()
                        failed_count = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'failed'
                        ).count()
                        
                        if processing_count > 0 or published_count > 0 or failed_count > 0:
                            plan.status = 'publishing'
                        else:
                            plan.status = 'pending'
                        plan.published_count = published_count
                        plan.pending_count = plan.video_count - published_count
                        plan.failed_count = failed_count
                        plan.updated_at = now
                        
                        db.commit()
                        
                        print(f"[TASK POLL] 发布计划 {plan.id} 统计: 已发布={published_count}, 处理中={processing_count}, 失败={failed_count}, 待发布={plan.pending_count}")
                        
                    except Exception as e:
                        print(f"[TASK POLL] 处理发布计划 {plan.id} 错误: {e}")
                        import traceback
                        traceback.print_exc()
                        try:
                            plan.status = 'failed'
                            plan.updated_at = now
                            db.commit()
                        except:
                            pass
            
            publishing_plans = db.query(PublishPlan).filter(
                PublishPlan.status == 'publishing'
            ).all()
            
            for plan in publishing_plans:
                try:
                    pending_videos = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'pending'
                    ).all()
                    
                    if not pending_videos:
                        continue
                    
                    print(f"[TASK POLL] 发布计划 {plan.id} 还有 {len(pending_videos)} 个待处理视频")
                    
                    from models import Account
                    accounts = db.query(Account).filter(
                        Account.platform == plan.platform,
                        Account.login_status == 'logged_in'
                    ).all()
                    
                    if not accounts:
                        print(f"[TASK POLL] 发布计划 {plan.id} 没有已登录账号，标记剩余视频为失败")
                        for video in pending_videos:
                            video.status = 'failed'
                        plan.failed_count = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'failed'
                        ).count()
                        plan.pending_count = 0
                        db.commit()
                        continue
                    
                    from pathlib import Path
                    import os
                    
                    for i, video in enumerate(pending_videos):
                        if video.publish_time and video.publish_time > now:
                            print(f"[TASK POLL] PlanVideo {video.id} 发布时间未到 ({video.publish_time})，跳过")
                            continue
                        
                        existing_task = db.query(VideoTask).filter(
                            VideoTask.plan_video_id == video.id
                        ).first()
                        
                        if existing_task:
                            print(f"[TASK POLL] PlanVideo {video.id} 已有任务 {existing_task.id}，跳过")
                            continue
                        
                        video_path = video.video_url
                        file_exists = False
                        
                        if video_path.startswith('http://') or video_path.startswith('https://'):
                            file_exists = True
                        else:
                            if video_path.startswith('file://'):
                                video_path = video_path[7:]
                            elif video_path.startswith('/'):
                                backend_dir = Path(__file__).parent.parent
                                if video_path.startswith('/uploads/'):
                                    uploads_path = backend_dir.parent / 'uploads'
                                    full_path = uploads_path / video_path.lstrip('/uploads/')
                                    video_path = str(full_path)
                                else:
                                    video_path = str(backend_dir / video_path.lstrip('/'))
                            file_exists = os.path.exists(video_path)
                        
                        if file_exists:
                            account = accounts[i % len(accounts)]
                            
                            video_task = VideoTask(
                                account_id=account.id,
                                device_id=account.device_id,
                                video_url=video.video_url,
                                video_title=video.video_title or f"视频 {i+1}",
                                thumbnail_url=video.thumbnail_url,
                                status='pending',
                                plan_video_id=video.id
                            )
                            db.add(video_task)
                            db.flush()
                            video.status = 'processing'
                            print(f"[TASK POLL] 为 PlanVideo {video.id} 创建 VideoTask，账号: {account.account_name}")
                        else:
                            print(f"[TASK POLL] 视频文件不存在，标记为失败: {video.video_url}")
                            video.status = 'failed'
                    
                    published_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'published'
                    ).count()
                    processing_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'processing'
                    ).count()
                    failed_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'failed'
                    ).count()
                    
                    plan.published_count = published_count
                    plan.pending_count = plan.video_count - published_count
                    plan.failed_count = failed_count
                    plan.updated_at = now
                    
                    db.commit()
                    
                    print(f"[TASK POLL] 发布计划 {plan.id} 统计: 已发布={published_count}, 处理中={processing_count}, 失败={failed_count}, 待发布={plan.pending_count}")
                    
                except Exception as e:
                    print(f"[TASK POLL] 处理 publishing 计划 {plan.id} 错误: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 1.6 检查超时的视频（每条视频在计划发布时间后45秒未完成则标记失败）
            TIMEOUT_SECONDS = 45
            timeout_plans = db.query(PublishPlan).filter(
                PublishPlan.status.in_(['pending', 'publishing'])
            ).all()
            for plan in timeout_plans:
                try:
                    candidates = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status.in_(['pending', 'processing'])
                    ).all()

                    changed = False
                    for video in candidates:
                        due_time = video.publish_time or plan.publish_time
                        if not due_time:
                            # 无计划时间的不做45秒超时判定（立即发布场景）
                            continue
                        if now <= (due_time + timedelta(seconds=TIMEOUT_SECONDS)):
                            continue

                        video.status = 'failed'
                        changed = True
                        print(f"[TASK POLL] PlanVideo {video.id} 超时(>{TIMEOUT_SECONDS}s)，标记为失败")

                        # 同步停止并标记关联上传任务，避免继续回写成功状态
                        timeout_tasks = db.query(VideoTask).filter(
                            VideoTask.plan_video_id == video.id,
                            VideoTask.status.in_(['pending', 'uploading', 'processing'])
                        ).all()
                        for task in timeout_tasks:
                            task.status = 'failed'
                            task.error_message = f"计划发布时间后{TIMEOUT_SECONDS}秒内未发布完成，系统已停止并标记失败"
                            task.completed_at = now
                            print(f"[TASK POLL] VideoTask {task.id} 因超时标记为 failed")

                    if not changed:
                        continue
                    
                    published_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'published'
                    ).count()
                    failed_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'failed'
                    ).count()
                    pending_only_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'pending'
                    ).count()
                    processing_count = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'processing'
                    ).count()
                    
                    plan.published_count = published_count
                    plan.failed_count = failed_count
                    plan.pending_count = plan.video_count - published_count
                    
                    if pending_only_count == 0 and processing_count == 0:
                        if published_count > 0 and failed_count > 0:
                            plan.status = 'partial_completed'
                            print(f"[TASK POLL] 发布计划 {plan.id} 部分完成")
                        elif failed_count > 0:
                            plan.status = 'failed'
                            print(f"[TASK POLL] 发布计划 {plan.id} 全部失败")
                    
                    db.commit()
                    
                except Exception as e:
                    print(f"[TASK POLL] 检查超时视频错误: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 2. 处理定时发布任务（publish_date 已到的任务）
            now = datetime.now()
            scheduled_tasks = db.query(VideoTask).filter(
                VideoTask.status == 'pending',
                VideoTask.publish_date <= now
            ).all()
            
            if scheduled_tasks:
                print(f"[TASK POLL] 发现 {len(scheduled_tasks)} 个到期的定时发布任务")
                
                for task in scheduled_tasks:
                    try:
                        print(f"[TASK POLL] 处理定时发布任务: {task.video_title} (ID: {task.id})")
                        # 将任务的publish_date设置为None，变为立即发布任务
                        task.publish_date = None
                        db.commit()
                        print(f"[TASK POLL] 定时发布任务 {task.id} 已转为立即发布任务")
                    except Exception as e:
                        print(f"[TASK POLL] 处理定时发布任务 {task.id} 错误: {e}")
                        import traceback
                        traceback.print_exc()
            
            # 3. 处理立即发布任务
            self._process_video_tasks(db)
            
            # 处理对话发送任务
            chat_tasks = db.query(ChatTask).filter(
                ChatTask.status == 'pending'
            ).limit(10).all()
            
            for task in chat_tasks:
                try:
                    # 在后台线程中执行
                    import asyncio
                    thread = threading.Thread(
                        target=lambda: asyncio.run(execute_chat_send(task.id)),
                        daemon=True
                    )
                    thread.start()
                except Exception as e:
                    print(f"启动对话发送任务 {task.id} 失败: {e}")
            
            # 处理监听任务
            listen_tasks = db.query(ListenTask).filter(
                ListenTask.status == 'pending'
            ).limit(10).all()
            
            for task in listen_tasks:
                try:
                    # 在后台线程中执行
                    import asyncio
                    if task.action == 'start':
                        thread = threading.Thread(
                            target=lambda: asyncio.run(execute_listen_start(task.id)),
                            daemon=True
                        )
                    elif task.action == 'stop':
                        thread = threading.Thread(
                            target=lambda: asyncio.run(execute_listen_stop(task.id)),
                            daemon=True
                        )
                    else:
                        continue
                    thread.start()
                except Exception as e:
                    print(f"启动监听任务 {task.id} 失败: {e}")


# 全局任务处理器实例
_task_processor = None

def get_task_processor() -> TaskProcessor:
    """获取任务处理器实例（单例）"""
    global _task_processor
    if _task_processor is None:
        _task_processor = TaskProcessor()
    return _task_processor
