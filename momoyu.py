import requests
from bs4 import BeautifulSoup
import asyncio
import aiohttp
import schedule
import threading
import time
import re
from plugins import register, Plugin, Event, Reply, ReplyType, logger
from channel.wrest import WrestChannel



@register
class Momoyu(Plugin):
    name = "momoyu"

    def __init__(self, config):
        super().__init__(config)
        self.scheduler_thread = None
        self.start_schedule()

    def did_receive_message(self, event: Event):
        # 处理消息内容
        content = event.message.content
        if isinstance(content, dict):  # 如果内容是字典
            query = content.get("text", "").strip()
        elif isinstance(content, str):  # 如果内容是字符串
            query = content.strip()
        else:
            logger.error("Unexpected message content type.")
            return

        is_group = event.message.is_group
        if is_group:
            query = re.sub(r'@[\w]+\s+', '', query, count=1).strip()


        commands = self.config.get("command", [])
        if any(re.search(r'\b' + re.escape(cmd) + r'\b', query) for cmd in commands):
            if query in ["早报", "新闻", "来点新闻", "今天新闻"]:
                reply = self.get_daily_news()
                event.channel.send(reply, event.message)
                event.bypass()            
        else:
            pass

    def start_schedule(self):
        if self.scheduler_thread is None:
            schedule_times = self.config.get("schedule_time", [])
            if schedule_times:
                self.scheduler_thread = threading.Thread(target=self.run_schedule)
                self.scheduler_thread.start()
            else:
                logger.info("定时推送已取消")

    def run_schedule(self):
        schedule_times = self.config.get("schedule_time", [])
        if not isinstance(schedule_times, list):
            logger.error("schedule_time 配置应为列表格式")
            return
        
        # 遍历所有时间点，设置调度
        for schedule_time in schedule_times:
            try:
                schedule.every().day.at(schedule_time).do(self.daily_push)
                logger.info(f"定时任务已设置：{schedule_time}")
            except Exception as e:
                logger.error(f"设置定时任务失败：{schedule_time}, 错误: {e}")

        # 启动调度循环
        while True:
            schedule.run_pending()
            time.sleep(1)

    def get_daily_news(self):

        momoyu_rss = self.config.get("momoyu_rss")
        xml_content = self.get_rss_content(momoyu_rss)
        if not xml_content:
            error_info = "无法获取RSS内容，请稍后重试。"
            return error_info

        # 解析内容
        categories = self.parse_xml_content(xml_content)
        if not categories:
            error_info = "解析RSS内容失败。"
            return error_info

        # 为每个标题添加emoji
        reply = asyncio.run(self.process_categories(categories))
        return reply
        

    def get_rss_content(self, url):
        """获取RSS链接的实时内容"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"获取RSS内容时出错: {e}")
            return None

    def parse_xml_content(self, xml_content):
        """解析XML内容并提取不同类别的热搜标题"""
        enabled_categories = self.config.get("categories", {})
        try:
            soup = BeautifulSoup(xml_content, 'xml')
            item = soup.find('item')
            if not item or not item.find('description'):
                logger.warning("未找到有效的item或description")
                return None

            description = item.find('description').text
            content_soup = BeautifulSoup(description, 'html.parser')

            results = {category: [] for category, enabled in enabled_categories.items() if enabled}

            current_category = None

            for element in content_soup.find_all(['h2', 'p']):
                if element.name == 'h2':
                    current_category = element.text.strip()
                elif element.name == 'p' and current_category:
                    link = element.find('a')
                    if link and current_category in results:
                        # 添加标题到结果中
                        title = re.sub(r'^\d+\.\s*', '', link.text.strip())
                        results[current_category].append(title)
            return results
        except Exception as e:
            logger.error(f"解析内容时出错: {e}")
            return None

    async def get_emoji_for_titles(self, titles, client_session):
        """批量请求 OpenAI API，为多个标题生成表情符号"""
        api_base = self.config.get("api_base")
        api_key = self.config.get("api_key")
        try:
            async with client_session.post(
                url=f"{api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{
                        "role": "system",
                        "content": "你是一个emoji助手。请为以下的新闻标题分别选择一个最合适的emoji。每个标题用换行分隔，返回的结果按行分开，一行一个emoji。"
                    }, {
                        "role": "user",
                        "content": "\n".join(titles)
                    }],
                    "max_tokens": 10 * len(titles)  # 为每个标题分配合理的 token 数
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # 按行分隔返回的结果
                    emojis = data['choices'][0]['message']['content'].strip().split("\n")
                    return [f"{emoji.strip()} {title}" for emoji, title in zip(emojis, titles)]
                return titles
        except Exception as e:
            logger.error(f"批量获取emoji时出错: {e}")
            return titles

    async def process_titles(self, titles, client_session):
        """异步处理一组标题，使用批量请求"""
        return await self.get_emoji_for_titles(titles, client_session)

    async def process_categories(self, categories):
        """为每个类别的标题添加emoji"""
        async with aiohttp.ClientSession() as session:
            result = ""
            for category, titles in categories.items():
                if titles:
                    processed_titles = await self.process_titles(titles, session)
                    result += f"\n\n==== {category} ====\n" + "\n".join(processed_titles)
            reply = Reply(ReplyType.TEXT, result)
            return reply

    def daily_push(self):
        schedule_time = self.config.get("schedule_time")
        if not schedule_time:
            logger.info("定时推送已取消")
            return

        single_chat_list = self.config.get("single_chat_list", [])
        group_chat_list = self.config.get("group_chat_list", [])
        reply = self.get_daily_news()
        if reply is None:
            logger.info("未获取到早报内容，本次定时推送跳过")
            return

        # 确保 reply 是字符串
        reply_content = reply.content if isinstance(reply, Reply) else reply
        self.push_to_chat(reply_content, single_chat_list, group_chat_list)

    def push_to_chat(self, reply_content, single_chat_list, group_chat_list):
        channel = WrestChannel()

		# 遍历列表，发送消息
        for chat_id in single_chat_list + group_chat_list:
            channel.send_txt(reply_content, chat_id)
            logger.info(f"摸摸鱼已发送到用户 {chat_id}")


    def will_decorate_reply(self, event: Event):
        pass

    def will_send_reply(self, event: Event):
        pass

    def will_generate_reply(self, event: Event):
        pass

    def help(self, **kwargs) -> str:
        return "每日定时或手动发送摸摸鱼"