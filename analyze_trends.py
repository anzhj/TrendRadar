# coding=utf-8
"""
热点趋势分析脚本
分析最近几天的数据，生成热点变化趋势和投资建议
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import pytz
import yaml


def load_config():
    """加载配置文件"""
    config_path = "config/config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    
    # 构建简化配置
    config = {
        "PLATFORMS": config_data["platforms"],
    }
    
    # 通知渠道配置
    notification = config_data.get("notification", {})
    webhooks = notification.get("webhooks", {})
    
    config["FEISHU_WEBHOOK_URL"] = os.environ.get("FEISHU_WEBHOOK_URL", "").strip() or webhooks.get("feishu_url", "")
    config["DINGTALK_WEBHOOK_URL"] = os.environ.get("DINGTALK_WEBHOOK_URL", "").strip() or webhooks.get("dingtalk_url", "")
    config["WEWORK_WEBHOOK_URL"] = os.environ.get("WEWORK_WEBHOOK_URL", "").strip() or webhooks.get("wework_url", "")
    config["TELEGRAM_BOT_TOKEN"] = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or webhooks.get("telegram_bot_token", "")
    config["TELEGRAM_CHAT_ID"] = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or webhooks.get("telegram_chat_id", "")
    config["EMAIL_FROM"] = os.environ.get("EMAIL_FROM", "").strip() or webhooks.get("email_from", "")
    config["EMAIL_PASSWORD"] = os.environ.get("EMAIL_PASSWORD", "").strip() or webhooks.get("email_password", "")
    config["EMAIL_TO"] = os.environ.get("EMAIL_TO", "").strip() or webhooks.get("email_to", "")
    config["BARK_URL"] = os.environ.get("BARK_URL", "").strip() or webhooks.get("bark_url", "")
    
    # AI 分析配置
    ai_config = config_data.get("ai_analysis", {})
    config["AI_ENABLED"] = os.environ.get("AI_ENABLED", "").strip().lower() in ("true", "1") if os.environ.get("AI_ENABLED", "").strip() else ai_config.get("enabled", False)
    config["AI_PROVIDER"] = os.environ.get("AI_PROVIDER", "").strip() or ai_config.get("provider", "openai")
    config["AI_API_KEY"] = os.environ.get("AI_API_KEY", "").strip() or ai_config.get("api_key", "")
    config["AI_MODEL"] = os.environ.get("AI_MODEL", "").strip() or ai_config.get("model", "gpt-4o-mini")
    config["AI_BASE_URL"] = os.environ.get("AI_BASE_URL", "").strip() or ai_config.get("base_url", "")
    
    return config


CONFIG = load_config()


def get_beijing_time():
    """获取北京时间"""
    return datetime.now(pytz.timezone("Asia/Shanghai"))


def get_recent_dates(days: int = 3) -> List[str]:
    """获取最近N天的日期文件夹名称"""
    beijing_time = get_beijing_time()
    dates = []
    for i in range(days):
        date = beijing_time - timedelta(days=i)
        dates.append(date.strftime("%Y年%m月%d日"))
    return dates


def clean_title(title: str) -> str:
    """清理标题"""
    if not isinstance(title, str):
        title = str(title)
    cleaned = title.replace("\n", " ").replace("\r", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_txt_file(file_path: Path) -> Dict:
    """解析单个txt文件"""
    titles_by_source = {}
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        sections = content.split("\n\n")
        
        for section in sections:
            if not section.strip() or "==== 以下ID请求失败 ====" in section:
                continue
            
            lines = section.strip().split("\n")
            if len(lines) < 2:
                continue
            
            # 解析来源ID
            header = lines[0].strip()
            if " | " in header:
                source_id = header.split(" | ")[0].strip()
            else:
                source_id = header
            
            titles_by_source[source_id] = []
            
            # 解析标题
            for line in lines[1:]:
                if line.strip():
                    try:
                        # 提取排名和标题
                        if ". " in line and line.split(". ")[0].isdigit():
                            rank_str, title_part = line.split(". ", 1)
                            rank = int(rank_str)
                        else:
                            rank = 999
                            title_part = line
                        
                        # 提取 URL 和 MOBILE URL
                        url = ""
                        mobile_url = ""
                        
                        if " [MOBILE:" in title_part:
                            title_part, mobile_part = title_part.rsplit(" [MOBILE:", 1)
                            if mobile_part.endswith("]"):
                                mobile_url = mobile_part[:-1]
                        
                        if " [URL:" in title_part:
                            title_part, url_part = title_part.rsplit(" [URL:", 1)
                            if url_part.endswith("]"):
                                url = url_part[:-1]
                        
                        title = clean_title(title_part.strip())
                        if title:
                            titles_by_source[source_id].append({
                                "title": title,
                                "rank": rank,
                                "url": url,
                                "mobileUrl": mobile_url
                            })
                    except Exception as e:
                        print(f"解析标题行出错: {line}, 错误: {e}")
    
    return titles_by_source


def load_daily_data(date_folder: str) -> Dict:
    """加载某一天的所有数据"""
    output_dir = Path("output") / date_folder / "txt"
    
    if not output_dir.exists():
        return {}
    
    all_titles = defaultdict(lambda: defaultdict(lambda: {"count": 0, "ranks": [], "times": []}))
    
    txt_files = sorted([f for f in output_dir.iterdir() if f.suffix == ".txt"])
    
    for txt_file in txt_files:
        time_info = txt_file.stem  # 例如: "08时30分"
        titles_by_source = parse_txt_file(txt_file)
        
        for source_id, titles in titles_by_source.items():
            for item in titles:
                title = item["title"]
                rank = item["rank"]
                url = item.get("url", "")
                mobile_url = item.get("mobileUrl", "")
                
                all_titles[source_id][title]["count"] += 1
                all_titles[source_id][title]["ranks"].append(rank)
                all_titles[source_id][title]["times"].append(time_info)
                
                # 保存 URL 信息（如果还没有的话）
                if not all_titles[source_id][title].get("url") and url:
                    all_titles[source_id][title]["url"] = url
                if not all_titles[source_id][title].get("mobileUrl") and mobile_url:
                    all_titles[source_id][title]["mobileUrl"] = mobile_url
    
    return dict(all_titles)


def analyze_trends(days: int = 3) -> Dict:
    """分析最近N天的热点趋势"""
    dates = get_recent_dates(days)
    
    # 加载每天的数据
    daily_data = {}
    for date in dates:
        data = load_daily_data(date)
        if data:
            daily_data[date] = data
    
    if not daily_data:
        return {"error": "没有找到可分析的数据"}
    
    # 统计热点词频
    all_keywords = defaultdict(lambda: {"total_count": 0, "daily_counts": {}, "titles": []})
    
    for date, sources in daily_data.items():
        for source_id, titles in sources.items():
            for title, info in titles.items():
                # 提取关键词（简单实现：取标题中的词）
                keywords = extract_keywords(title)
                
                for keyword in keywords:
                    all_keywords[keyword]["total_count"] += info["count"]
                    if date not in all_keywords[keyword]["daily_counts"]:
                        all_keywords[keyword]["daily_counts"][date] = 0
                    all_keywords[keyword]["daily_counts"][date] += info["count"]
                    
                    all_keywords[keyword]["titles"].append({
                        "title": title,
                        "date": date,
                        "source": source_id,
                        "count": info["count"],
                        "avg_rank": sum(info["ranks"]) / len(info["ranks"]) if info["ranks"] else 999,
                        "url": info.get("url", ""),
                        "mobileUrl": info.get("mobileUrl", "")
                    })
    
    # 分析热点变化
    trending_up = []  # 上升趋势
    trending_down = []  # 下降趋势
    hot_topics = []  # 持续热点
    new_topics = []  # 新出现的热点
    
    for keyword, data in all_keywords.items():
        # 过滤：关键词长度至少4个字，总出现次数至少5次
        if len(keyword) < 4 or data["total_count"] < 5:
            continue
        
        daily_counts = data["daily_counts"]
        dates_sorted = sorted(daily_counts.keys(), reverse=True)
        
        if len(dates_sorted) >= 2:
            recent_count = daily_counts.get(dates_sorted[0], 0)
            previous_count = daily_counts.get(dates_sorted[1], 0)
            
            # 计算变化率
            if previous_count > 0:
                change_rate = (recent_count - previous_count) / previous_count
            else:
                change_rate = 1.0 if recent_count > 0 else 0
            
            # 计算平均排名（越小越重要）
            avg_rank = sum(t["avg_rank"] for t in data["titles"]) / len(data["titles"])
            
            item = {
                "keyword": keyword,
                "total_count": data["total_count"],
                "recent_count": recent_count,
                "previous_count": previous_count,
                "change_rate": change_rate,
                "avg_rank": avg_rank,
                "titles": sorted(data["titles"], key=lambda x: x["avg_rank"])[:2]  # 取排名最高的2条
            }
            
            # 新出现的热点（之前没有，现在突然出现）
            if previous_count == 0 and recent_count >= 5:
                new_topics.append(item)
            # 上升趋势（增长超过100%，且最近出现至少5次）
            elif change_rate > 1.0 and recent_count >= 5:
                trending_up.append(item)
            # 下降趋势（下降超过50%）
            elif change_rate < -0.5 and previous_count >= 5:
                trending_down.append(item)
            # 持续热点（连续多天出现，总计至少15次，且排名靠前）
            elif len(dates_sorted) >= 2 and data["total_count"] >= 15 and avg_rank < 20:
                hot_topics.append(item)
        elif len(dates_sorted) == 1:
            # 只在最近一天出现的新话题
            recent_count = daily_counts.get(dates_sorted[0], 0)
            if recent_count >= 8:  # 单日出现至少8次才算新热点
                avg_rank = sum(t["avg_rank"] for t in data["titles"]) / len(data["titles"])
                new_topics.append({
                    "keyword": keyword,
                    "total_count": data["total_count"],
                    "recent_count": recent_count,
                    "previous_count": 0,
                    "change_rate": 0,
                    "avg_rank": avg_rank,
                    "titles": sorted(data["titles"], key=lambda x: x["avg_rank"])[:2]
                })
    
    # 去重函数：移除相似的关键词
    def deduplicate_keywords(items: List[Dict]) -> List[Dict]:
        """去除相似的关键词，保留最重要的"""
        if not items:
            return []
        
        result = []
        seen_keywords = set()
        
        for item in items:
            keyword = item["keyword"]
            # 检查是否与已有关键词过于相似
            is_similar = False
            for seen in seen_keywords:
                # 如果一个关键词包含另一个，或者相似度很高，认为是重复
                if keyword in seen or seen in keyword:
                    is_similar = True
                    break
                # 计算相似度（简单的字符重叠比例）
                common = sum(1 for c in keyword if c in seen)
                similarity = common / max(len(keyword), len(seen))
                if similarity > 0.7:
                    is_similar = True
                    break
            
            if not is_similar:
                result.append(item)
                seen_keywords.add(keyword)
        
        return result
    
    # 排序
    # 上升趋势：按变化率和最近出现次数综合排序
    trending_up.sort(key=lambda x: (x["change_rate"] * x["recent_count"], -x["avg_rank"]), reverse=True)
    trending_up = deduplicate_keywords(trending_up)
    
    # 新话题：按出现次数和排名排序
    new_topics.sort(key=lambda x: (x["recent_count"], -x["avg_rank"]), reverse=True)
    new_topics = deduplicate_keywords(new_topics)
    
    # 下降趋势：按变化率排序
    trending_down.sort(key=lambda x: x["change_rate"])
    trending_down = deduplicate_keywords(trending_down)
    
    # 持续热点：按总出现次数和排名排序
    hot_topics.sort(key=lambda x: (x["total_count"], -x["avg_rank"]), reverse=True)
    hot_topics = deduplicate_keywords(hot_topics)
    
    return {
        "analysis_date": get_beijing_time().strftime("%Y年%m月%d日 %H:%M"),
        "days_analyzed": len(daily_data),
        "date_range": f"{dates[-1]} 至 {dates[0]}",
        "new_topics": new_topics[:8],
        "trending_up": trending_up[:8],
        "trending_down": trending_down[:8],
        "hot_topics": hot_topics[:10],
        "total_keywords": len(all_keywords)
    }


def extract_keywords(title: str) -> List[str]:
    """从标题中提取关键词（优化版 - 基于完整词汇）"""
    import re
    
    # 扩展停用词列表
    stop_words = {
        "的", "了", "在", "是", "和", "与", "及", "等", "将", "被", "为", "有", "对", "从", "到", 
        "中", "上", "下", "个", "人", "年", "月", "日", "时", "分", "秒", "这", "那", "些", "此",
        "之", "其", "或", "而", "但", "因", "所", "以", "于", "由", "也", "都", "把", "向", "往",
        "给", "让", "使", "得", "着", "过", "去", "来", "要", "会", "能", "可", "就", "还", "又",
        "再", "更", "很", "最", "太", "非", "不", "没", "无", "未", "已", "曾", "正", "在", "正在",
        "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万", "亿",
        "第", "次", "位", "名", "条", "则", "项", "件", "篇", "章", "节", "段", "句", "字", "词",
        "今", "明", "昨", "前", "后", "早", "晚", "新", "旧", "老", "小", "大", "多", "少", "高", "低",
        "长", "短", "快", "慢", "好", "坏", "美", "丑", "真", "假", "对", "错", "是", "非",
        "男", "女", "子", "为", "与", "及", "或", "且", "但", "却", "而", "则", "乃", "至", "若",
        "如", "比", "像", "似", "同", "异", "别", "各", "每", "某", "何", "谁", "什", "哪", "怎",
        "为何", "如何", "怎样", "怎么", "什么", "哪里", "哪儿", "多少", "几", "若干", "丨", "｜"
    }
    
    # 先按标点符号分割成短语
    # 保留中文、英文、数字，其他都作为分隔符
    phrases = re.split(r'[^\w\s]+', title)
    phrases = [p.strip() for p in phrases if p.strip()]
    
    keywords = []
    
    for phrase in phrases:
        # 跳过太短或太长的短语
        if len(phrase) < 4 or len(phrase) > 20:
            continue
        
        # 跳过包含停用词的短语
        if any(sw in phrase for sw in stop_words):
            continue
        
        # 跳过纯数字
        if phrase.isdigit():
            continue
        
        # 跳过包含过多数字的短语
        digit_count = sum(c.isdigit() for c in phrase)
        if digit_count > len(phrase) * 0.5:
            continue
        
        keywords.append(phrase)
    
    # 如果没有提取到关键词，尝试提取标题中的核心词组
    if not keywords:
        # 移除所有标点和空格
        cleaned = re.sub(r'[^\w]', '', title)
        
        # 提取6-10字的词组
        for length in [10, 9, 8, 7, 6]:
            if len(cleaned) >= length:
                for i in range(len(cleaned) - length + 1):
                    word = cleaned[i:i+length]
                    if not any(sw in word for sw in stop_words) and not word.isdigit():
                        keywords.append(word)
                        if len(keywords) >= 2:
                            break
            if len(keywords) >= 2:
                break
    
    # 去重并限制数量
    unique_keywords = list(dict.fromkeys(keywords))
    return unique_keywords[:2]  # 只返回最多2个关键词


def generate_investment_advice(analysis: Dict) -> str:
    """生成投资建议"""
    if "error" in analysis:
        return analysis["error"]
    
    advice = []
    
    # 新出现的热点
    if analysis.get("new_topics"):
        advice.append("🆕 **新出现热点（重点关注）**")
        for i, item in enumerate(analysis["new_topics"][:5], 1):
            avg_rank = item.get("avg_rank", 999)
            advice.append(f"{i}. {item['keyword']} (新出现{item['recent_count']}次, 平均排名{avg_rank:.0f})")
            if item["titles"]:
                title = item['titles'][0]['title']
                # 截取标题，避免过长
                display_title = title[:60] + "..." if len(title) > 60 else title
                advice.append(f"   📰 {display_title}")
    
    # 上升趋势分析
    if analysis["trending_up"]:
        advice.append("\n📈 **快速上升热点（积极关注）**")
        for i, item in enumerate(analysis["trending_up"][:5], 1):
            change_pct = item["change_rate"] * 100
            avg_rank = item.get("avg_rank", 999)
            advice.append(f"{i}. {item['keyword']} (热度↑{change_pct:.0f}%, 最近{item['recent_count']}次, 排名{avg_rank:.0f})")
            if item["titles"]:
                title = item['titles'][0]['title']
                display_title = title[:60] + "..." if len(title) > 60 else title
                advice.append(f"   📰 {display_title}")
    
    # 持续热点
    if analysis["hot_topics"]:
        advice.append("\n🔥 **持续热点（稳定配置）**")
        for i, item in enumerate(analysis["hot_topics"][:5], 1):
            avg_rank = item.get("avg_rank", 999)
            advice.append(f"{i}. {item['keyword']} (总计{item['total_count']}次, 平均排名{avg_rank:.0f})")
            if item["titles"]:
                title = item['titles'][0]['title']
                display_title = title[:60] + "..." if len(title) > 60 else title
                advice.append(f"   📰 {display_title}")
    
    # 下降趋势
    if analysis["trending_down"]:
        advice.append("\n📉 **降温话题（谨慎观望）**")
        for i, item in enumerate(analysis["trending_down"][:5], 1):
            change_pct = abs(item["change_rate"]) * 100
            advice.append(f"{i}. {item['keyword']} (热度↓{change_pct:.0f}%, 之前{item['previous_count']}次→现在{item['recent_count']}次)")
    
    # 投资建议总结
    advice.append("\n" + "="*50)
    advice.append("💡 **投资建议总结**")
    advice.append("="*50)
    
    suggestions = []
    
    if analysis.get("new_topics"):
        top_new = analysis["new_topics"][0]["keyword"]
        suggestions.append(f"🎯 **新机会**: {top_new} 等新话题突然出现，建议密切关注相关领域动态")
    
    if analysis["trending_up"]:
        top_trending = analysis["trending_up"][0]["keyword"]
        suggestions.append(f"📈 **上升机会**: {top_trending} 等话题热度快速上升，可考虑提前布局")
    
    if analysis["hot_topics"]:
        hot_keywords = ", ".join([item['keyword'] for item in analysis['hot_topics'][:3]])
        suggestions.append(f"🔥 **稳定配置**: {hot_keywords} 等持续热门，适合稳健投资")
    
    if analysis["trending_down"]:
        down_keywords = ", ".join([item['keyword'] for item in analysis['trending_down'][:2]])
        suggestions.append(f"⚠️  **风险提示**: {down_keywords} 等话题热度下降，建议谨慎观望")
    
    if not suggestions:
        suggestions.append("📊 当前数据不足，建议继续观察市场动态")
    
    advice.extend(suggestions)
    
    return "\n".join(advice)


def format_report(analysis: Dict) -> str:
    """格式化分析报告"""
    # 计算总新闻数
    total_news = 0
    for item in analysis.get('new_topics', []):
        total_news += item.get('total_count', 0)
    for item in analysis.get('trending_up', []):
        total_news += item.get('total_count', 0)
    for item in analysis.get('hot_topics', []):
        total_news += item.get('total_count', 0)
    for item in analysis.get('trending_down', []):
        total_news += item.get('total_count', 0)
    
    # 获取当前时间
    now = get_beijing_time()
    
    report = []
    report.append("TrendRadar AI 投资建议")
    report.append("")
    report.append(f"总新闻数： {total_news}")
    report.append("")
    report.append(f"时间： {now.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append(f"类型： AI 投资分析报告")
    report.append("")
    report.append("---")
    report.append("")
    report.append("=" * 50)
    report.append("📊 热点趋势分析报告")
    report.append("=" * 50)
    report.append(f"分析时间: {analysis['analysis_date']}")
    report.append(f"数据范围: {analysis['date_range']} ({analysis['days_analyzed']}天)")
    report.append(f"关键词总数: {analysis['total_keywords']}")
    report.append("")
    
    advice = generate_investment_advice(analysis)
    report.append(advice)
    
    report.append("\n" + "=" * 50)
    
    return "\n".join(report)


import requests
import time


def send_analysis_report(report_text: str):
    """发送分析报告到各个通知渠道"""
    success_count = 0
    
    # 从报告文本中提取总新闻数
    total_news = 0
    for line in report_text.split('\n'):
        if '总新闻数：' in line:
            try:
                total_news = int(line.split('总新闻数：')[1].strip().split()[0])
            except:
                pass
            break
    
    # 获取当前时间
    now = get_beijing_time()
    
    # 飞书
    if CONFIG.get("FEISHU_WEBHOOK_URL"):
        try:
            payload = {
                "msg_type": "text",
                "content": {
                    "total_titles": total_news,
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "report_type": "AI 投资分析报告",
                    "text": report_text
                }
            }
            response = requests.post(CONFIG["FEISHU_WEBHOOK_URL"], json=payload, timeout=10)
            if response.status_code == 200:
                print("✓ 已发送到飞书")
                success_count += 1
            else:
                print(f"✗ 飞书发送失败: {response.status_code}")
        except Exception as e:
            print(f"✗ 飞书发送失败: {e}")
    
    # 钉钉
    if CONFIG.get("DINGTALK_WEBHOOK_URL"):
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "热点趋势分析",
                    "text": report_text
                }
            }
            response = requests.post(CONFIG["DINGTALK_WEBHOOK_URL"], json=payload, timeout=10)
            if response.status_code == 200:
                print("✓ 已发送到钉钉")
                success_count += 1
            else:
                print(f"✗ 钉钉发送失败: {response.status_code}")
        except Exception as e:
            print(f"✗ 钉钉发送失败: {e}")
    
    # 企业微信
    if CONFIG.get("WEWORK_WEBHOOK_URL"):
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": report_text
                }
            }
            response = requests.post(CONFIG["WEWORK_WEBHOOK_URL"], json=payload, timeout=10)
            if response.status_code == 200:
                print("✓ 已发送到企业微信")
                success_count += 1
            else:
                print(f"✗ 企业微信发送失败: {response.status_code}")
        except Exception as e:
            print(f"✗ 企业微信发送失败: {e}")
    
    # Telegram
    if CONFIG.get("TELEGRAM_BOT_TOKEN") and CONFIG.get("TELEGRAM_CHAT_ID"):
        try:
            url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_BOT_TOKEN']}/sendMessage"
            payload = {
                "chat_id": CONFIG["TELEGRAM_CHAT_ID"],
                "text": report_text,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print("✓ 已发送到Telegram")
                success_count += 1
            else:
                print(f"✗ Telegram发送失败: {response.status_code}")
        except Exception as e:
            print(f"✗ Telegram发送失败: {e}")
    
    # Bark
    if CONFIG.get("BARK_URL"):
        try:
            # Bark URL格式: https://api.day.app/your_key/title/content
            bark_url = CONFIG["BARK_URL"].rstrip("/")
            title = "热点趋势分析"
            # 简化内容以适应Bark
            content = report_text[:500] + "..." if len(report_text) > 500 else report_text
            url = f"{bark_url}/{title}/{content}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print("✓ 已发送到Bark")
                success_count += 1
            else:
                print(f"✗ Bark发送失败: {response.status_code}")
        except Exception as e:
            print(f"✗ Bark发送失败: {e}")
    
    # 邮件（使用简单的SMTP）
    if CONFIG.get("EMAIL_FROM") and CONFIG.get("EMAIL_PASSWORD") and CONFIG.get("EMAIL_TO"):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = CONFIG["EMAIL_FROM"]
            msg['To'] = CONFIG["EMAIL_TO"]
            msg['Subject'] = "热点趋势分析报告"
            
            msg.attach(MIMEText(report_text, 'plain', 'utf-8'))
            
            # 自动识别SMTP服务器
            email_domain = CONFIG["EMAIL_FROM"].split("@")[1]
            smtp_configs = {
                "gmail.com": ("smtp.gmail.com", 587),
                "qq.com": ("smtp.qq.com", 465),
                "163.com": ("smtp.163.com", 465),
                "126.com": ("smtp.126.com", 465),
            }
            
            smtp_server, smtp_port = smtp_configs.get(email_domain, ("smtp." + email_domain, 587))
            
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                server.starttls()
            
            server.login(CONFIG["EMAIL_FROM"], CONFIG["EMAIL_PASSWORD"])
            server.send_message(msg)
            server.quit()
            
            print("✓ 已发送到邮箱")
            success_count += 1
        except Exception as e:
            print(f"✗ 邮件发送失败: {e}")
    
    if success_count == 0:
        print("⚠️  未配置任何通知渠道或所有渠道发送失败")
    else:
        print(f"\n✅ 成功发送到 {success_count} 个渠道")


def main():
    """主函数"""
    print("开始分析热点趋势...")
    
    # 分析最近3天的数据
    analysis = analyze_trends(days=3)
    
    # 生成报告
    report = format_report(analysis)
    
    # 打印报告
    print(report)
    
    # 保存报告到文件（按日期组织）
    beijing_time = get_beijing_time()
    date_folder = beijing_time.strftime("%Y年%m月%d日")
    output_dir = Path("output") / date_folder / "trends"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件名只包含时间，不包含日期（因为已经在文件夹名中）
    report_file = output_dir / f"trend_analysis_{beijing_time.strftime('%H%M')}.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n报告已保存到: {report_file}")
    
    # 发送通知
    if os.environ.get("ENABLE_NOTIFICATION", "true").lower() in ("true", "1"):
        print("\n正在发送通知...")
        send_analysis_report(report)
    else:
        print("\n通知功能已禁用")


if __name__ == "__main__":
    main()
