"""
后台任务处理器
按需处理待处理的任务，定时任务使用轻量级定时检查
"""
import threading
import time
import json
from datetime import datetime
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
            
            # 1. 检查到期的发布计划
            # 对于分阶段发布：检查是否有视频的 schedule_time 到期
            # 对于批量发布：检查计划的 publish_time 是否到期
            publish_plans_to_process = []
            
            # 先检查有 publish_time 的计划（批量发布）
            plans_with_publish_time = db.query(PublishPlan).filter(
                PublishPlan.status == 'pending',
                PublishPlan.publish_time <= now,
                PublishPlan.publish_time.isnot(None)
            ).limit(10).all()
            
            for plan in plans_with_publish_time:
                # 检查是否有视频的 schedule_time 到期（分阶段发布）
                # 如果有视频设置了 schedule_time，说明是分阶段发布，需要检查视频的 schedule_time
                videos_with_schedule = db.query(PlanVideo).filter(
                    PlanVideo.plan_id == plan.id,
                    PlanVideo.status == 'pending',
                    PlanVideo.schedule_time.isnot(None),
                    PlanVideo.schedule_time <= now
                ).count()
                
                # 如果没有视频设置 schedule_time，或者计划的 publish_time 到了，则处理
                # 如果有视频设置了 schedule_time，只有当有视频的 schedule_time 到期时才处理
                videos_total = db.query(PlanVideo).filter(PlanVideo.plan_id == plan.id).count()
                videos_with_schedule_total = db.query(PlanVideo).filter(
                    PlanVideo.plan_id == plan.id,
                    PlanVideo.schedule_time.isnot(None)
                ).count()
                
                # 如果所有视频都有 schedule_time，说明是分阶段发布，只检查视频的 schedule_time
                if videos_with_schedule_total > 0 and videos_with_schedule_total == videos_total:
                    # 分阶段发布：只有当有视频的 schedule_time 到期时才处理
                    if videos_with_schedule > 0:
                        publish_plans_to_process.append(plan)
                else:
                    # 批量发布或混合模式：计划的 publish_time 到了就处理
                    publish_plans_to_process.append(plan)
            
            # 检查没有 publish_time 但有视频 schedule_time 已到的计划（纯分阶段发布）
            plans_without_publish_time = db.query(PublishPlan).filter(
                PublishPlan.status == 'pending',
                PublishPlan.publish_time.is_(None)  # 计划的 publish_time 为空
            ).limit(10).all()
            
            if plans_without_publish_time:
                print(f"[定时检查] 检查 {len(plans_without_publish_time)} 个没有全局发布时间的计划（分阶段发布）")
            
            for plan in plans_without_publish_time:
                # 检查是否有视频的 schedule_time 到期
                videos_with_schedule = db.query(PlanVideo).filter(
                    PlanVideo.plan_id == plan.id,
                    PlanVideo.status == 'pending',
                    PlanVideo.schedule_time.isnot(None),
                    PlanVideo.schedule_time <= now
                ).all()
                
                if videos_with_schedule:
                    print(f"[定时检查] ✓ 发现分阶段发布计划 {plan.id} ({plan.plan_name}) 有 {len(videos_with_schedule)} 个视频的 schedule_time 已到期")
                    for v in videos_with_schedule:
                        print(f"  - 视频 {v.id}: schedule_time={v.schedule_time}, 当前时间={now}")
                    publish_plans_to_process.append(plan)
                else:
                    # 打印调试信息：只检查待发布的视频状态
                    pending_videos = db.query(PlanVideo).filter(
                        PlanVideo.plan_id == plan.id,
                        PlanVideo.status == 'pending'
                    ).all()
                    if pending_videos:
                        print(f"[定时检查] 计划 {plan.id} 的待发布视频状态检查:")
                        for v in pending_videos:
                            status_info = f"视频 {v.id}: status={v.status}, schedule_time={v.schedule_time}"
                            if v.schedule_time:
                                time_diff = (v.schedule_time - now).total_seconds()
                                status_info += f", 距离发布时间还有 {int(time_diff)} 秒"
                            print(f"  - {status_info}")
            
            if publish_plans_to_process:
                print(f"[定时检查] 发现 {len(publish_plans_to_process)} 个到期的发布计划，触发处理")
                # 触发完整处理（在后台线程中）
                def trigger_processing():
                    try:
                        self._process_pending_tasks()
                    except Exception as e:
                        print(f"[定时检查] 触发任务处理失败: {e}")
                        import traceback
                        traceback.print_exc()
                
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
            # 1. 处理发布计划
            # 对于批量发布：查找 publish_time 已到的计划
            # 对于分阶段发布：查找有视频 schedule_time 已到的计划（即使计划的 publish_time 为空）
            now = datetime.now()
            
            # 先查找有 publish_time 且已到的计划（批量发布）
            plans_with_publish_time = db.query(PublishPlan).filter(
                PublishPlan.status == 'pending',
                PublishPlan.publish_time <= now,
                PublishPlan.publish_time.isnot(None)
            ).all()
            
            # 查找没有 publish_time 的计划（分阶段发布）
            # 注意：对于分阶段发布，即使计划状态是 publishing，也应该继续检查是否有新的视频到期
            plans_without_publish_time = db.query(PublishPlan).filter(
                PublishPlan.publish_time.is_(None),  # 计划的 publish_time 为空
                PublishPlan.status.in_(['pending', 'publishing'])  # 允许 pending 和 publishing 状态
            ).all()
            
            # 检查这些计划是否有视频的 schedule_time 到期
            plans_with_video_schedule = []
            for plan in plans_without_publish_time:
                videos_ready = db.query(PlanVideo).filter(
                    PlanVideo.plan_id == plan.id,
                    PlanVideo.status == 'pending',
                    PlanVideo.schedule_time <= now,
                    PlanVideo.schedule_time.isnot(None)
                ).count()
                if videos_ready > 0:
                    plans_with_video_schedule.append(plan)
            
            # 合并两种类型的计划
            publish_plans = list(plans_with_publish_time) + plans_with_video_schedule
            
            if publish_plans:
                print(f"[TASK POLL] 发现 {len(publish_plans)} 个到期的发布计划")
                
                for plan in publish_plans:
                    try:
                        # 双重检查：确保计划状态是 pending 或 publishing（分阶段发布允许 publishing 状态继续处理）
                        db.refresh(plan)
                        if plan.status not in ['pending', 'publishing']:
                            print(f"[TASK POLL] 发布计划 {plan.id} 状态已变更为 {plan.status}，跳过处理（可能已完成或失败）")
                            continue
                        
                        print(f"[TASK POLL] 处理发布计划: {plan.plan_name} (ID: {plan.id}), 当前状态: {plan.status}")
                        # 如果状态是 pending，更新为 publishing（防止重复处理）
                        # 如果状态已经是 publishing（分阶段发布），保持 publishing 状态
                        if plan.status == 'pending':
                            plan.status = 'publishing'
                        plan.updated_at = now
                        db.commit()
                        
                        # 获取计划关联的视频
                        # 对于分阶段发布：只处理 schedule_time <= now 的视频
                        # 对于批量发布：处理所有 pending 状态的视频
                        video_query = db.query(PlanVideo).filter(
                            PlanVideo.plan_id == plan.id,
                            PlanVideo.status == 'pending'  # 只处理未发布的视频
                        )
                        
                        # 如果是分阶段发布，只处理到期的视频（schedule_time <= now）
                        # 如果视频没有 schedule_time，使用计划的 publish_time
                        plan_videos = []
                        for video in video_query.all():
                            # 确定该视频的发布时间
                            video_publish_time = video.schedule_time if video.schedule_time else plan.publish_time
                            # 如果没有发布时间，或者发布时间已到，则处理
                            if video_publish_time is None or video_publish_time <= now:
                                plan_videos.append(video)
                        
                        if not plan_videos:
                            print(f"[TASK POLL] 发布计划 {plan.id} 没有需要处理的视频（可能都在等待各自的发布时间），跳过")
                            # 检查是否所有视频都已处理完成
                            all_videos = db.query(PlanVideo).filter(PlanVideo.plan_id == plan.id).all()
                            if all_videos:
                                # 检查是否还有待处理的视频（可能在等待各自的发布时间）
                                pending_videos = [v for v in all_videos if v.status == 'pending']
                                if not pending_videos:
                                    plan.status = 'completed'
                                    print(f"[TASK POLL] 发布计划 {plan.id} 所有视频已处理完成，状态更新为 completed")
                                else:
                                    print(f"[TASK POLL] 发布计划 {plan.id} 还有 {len(pending_videos)} 个视频等待各自的发布时间")
                            else:
                                plan.status = 'completed'
                                print(f"[TASK POLL] 发布计划 {plan.id} 没有关联的视频，状态更新为 completed")
                            plan.updated_at = now
                            db.commit()
                            continue
                        
                        # 获取账号列表：优先使用计划中指定的账号，否则使用该平台下的所有已登录账号
                        from models import Account
                        import json as json_module  # 显式导入，避免作用域问题
                        account_ids_list = None
                        if plan.account_ids:
                            try:
                                account_ids_list = json_module.loads(plan.account_ids)
                                if not isinstance(account_ids_list, list) or len(account_ids_list) == 0:
                                    account_ids_list = None
                            except (ValueError, TypeError) as e:
                                print(f"[TASK POLL] 发布计划 {plan.id} 的 account_ids 格式错误: {e}，将使用所有已登录账号")
                                account_ids_list = None
                        
                        if account_ids_list:
                            # 使用指定的账号ID列表
                            accounts = db.query(Account).filter(
                                Account.id.in_(account_ids_list),
                                Account.platform == plan.platform,
                                Account.login_status == 'logged_in'
                            ).all()
                            print(f"[TASK POLL] 发布计划 {plan.id} 使用指定的 {len(accounts)} 个账号（从 {len(account_ids_list)} 个ID中选择）")
                        else:
                            # 使用该平台下的所有已登录账号
                            accounts = db.query(Account).filter(
                                Account.platform == plan.platform,
                                Account.login_status == 'logged_in'
                            ).all()
                            print(f"[TASK POLL] 发布计划 {plan.id} 使用该平台下的所有已登录账号（共 {len(accounts)} 个）")
                        
                        if not accounts:
                            print(f"[TASK POLL] 发布计划 {plan.id} 的平台 {plan.platform} 没有可用的已登录账号，跳过")
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
                                
                                # 检查是否已经存在相同的任务（相同的video_url和account_id，且状态不是completed）
                                existing_task = db.query(VideoTask).filter(
                                    VideoTask.video_url == video.video_url,
                                    VideoTask.account_id == account.id,
                                    VideoTask.status != 'completed'
                                ).first()
                                
                                if existing_task:
                                    print(f"[TASK POLL] 视频任务已存在（任务ID: {existing_task.id}, 状态: {existing_task.status}），处理策略中: {video.video_url}")
                                    
                                    # 如果任务已经在队列中待处理或正在处理中，视频标记为 processing，等待任务执行即可
                                    if existing_task.status in ['pending', 'uploading']:
                                        video.status = 'processing'
                                        continue
                                    
                                    # 如果任务之前失败了，则重置该任务为 pending，允许重新发布
                                    if existing_task.status == 'failed':
                                        print(f"[TASK POLL] 任务 {existing_task.id} 之前失败，本次将重置为 pending 重新发布")
                                        existing_task.status = 'pending'
                                        existing_task.started_at = None
                                        existing_task.completed_at = None
                                        existing_task.error_message = None
                                        video.status = 'processing'
                                        # 不再 continue，后续统计和任务处理会把该任务当作新的待处理任务
                                        continue
                                
                                # 处理 video_tags：如果是字符串（逗号分隔），转换为列表
                                video_tags_list = []
                                if video.video_tags:
                                    if isinstance(video.video_tags, str):
                                        # 尝试解析为JSON，如果不是JSON则按逗号分隔
                                        try:
                                            import json as json_module
                                            video_tags_list = json_module.loads(video.video_tags)
                                            if not isinstance(video_tags_list, list):
                                                video_tags_list = [video.video_tags]
                                        except (ValueError, TypeError):
                                            # 不是JSON，按逗号分隔（支持中文逗号和英文逗号）
                                            # 先替换中文逗号为英文逗号，然后分割
                                            tags_str = video.video_tags.replace('，', ',')  # 替换中文逗号为英文逗号
                                            video_tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                                    elif isinstance(video.video_tags, list):
                                        video_tags_list = video.video_tags
                                
                                # 创建视频任务
                                video_task = VideoTask(
                                    account_id=account.id,
                                    device_id=account.device_id,
                                    video_url=video.video_url,
                                    video_title=video.video_title or f"视频 {i+1}",
                                    video_description=video.video_description or '',  # 使用 PlanVideo 的正文
                                    video_tags=','.join(video_tags_list) if video_tags_list else None,  # 转换为逗号分隔的字符串
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
