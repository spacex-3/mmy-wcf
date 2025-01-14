# wechat-gptbot momoyu插件

本项目作为 `wechat-gptbot` 插件，可以根据关键字回复对应的信息。

可以配置类别和定时推送给特定的私聊或群聊；

## 安装指南

### 1. 添加插件源
在 `plugins/source.json` 文件中添加以下配置：
```
{
  "momoyu": {
    "repo": "https://github.com/spacex-3/mmy-wcf.git",
    "desc": "momoyu资讯"
  }
}
```

### 2. 插件配置
在 `config.json` 文件中添加以下配置：
```
"plugins": [
  {
    "name": "momoyu",
    "schedule_time": "09:30",
    "single_chat_list": ["wxid_123"],
    "group_chat_list": ["123@chatroom"],
    "command": ["早报", "新闻", "来点新闻", "今天新闻"],
    "api_base": "https://api.***.ai",
    "api_key": "sk-***",
    "momoyu_rss": "https://***",
    "categories": {
        "豆瓣热话": true,
        "微博热搜": true,
        "爱范儿": false,
        "虎嗅": true,
        "值得买3小时热门": true,
        "虎扑步行街": false,
        "36氪": true,
        "华尔街见闻": true,
        "直播吧": false,
        "懂车帝": true
  }
]
```
