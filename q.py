import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import json

# Intents設定
intents = discord.Intents.default()
intents.messages = intents.guilds = intents.members = intents.message_content = True

# Botのインスタンスを作成
bot = commands.Bot(command_prefix="/", intents=intents)

# チケット設定（ギルドごとの設定を保存）
settings = {key: {} for key in ["ticket", "panel_title", "panel_description", "panel_url", "staff_role", "developed_info", "dm_message", "embed_title", "embed_description", "embed_color", "link", "panel_image", "panel_color", "top_right_image", "developer_text", "developer_image", "open_image", "close_image", "allowed_roles"]}

def create_ticket_embed(title="チケットサポート", description="以下のボタンを押してチケットを開いてください。", **kwargs):
    embed = discord.Embed(title=title, description=description, color=kwargs.get("color", discord.Color.blue()))
    for key, value in kwargs.items():
        if value:
            if key in ["image_file", "thumbnail_file", "top_right_image_file", "developer_image_file"]:
                embed.set_image(url=f"attachment://{value.filename}")
            elif key == "developed_text":
                embed.set_footer(text=value, icon_url=kwargs.get("developed_icon_file"))
            elif key == "developer_text":
                embed.add_field(name="\u200b", value=value, inline=False)
            elif key == "thumbnail_url":
                embed.set_thumbnail(url=value)
    return embed

class TicketView(discord.ui.View):
    def __init__(self, options):
        super().__init__(timeout=None)
        self.add_item(TicketSelect(options))

class TicketSelect(discord.ui.Select):
    def __init__(self, options):
        select_options = [discord.SelectOption(label=option["name"], value=f"{option['category']}_{index}", description=option["description"], emoji=option["emoji"]) for index, option in enumerate(options)]
        super().__init__(placeholder="チケットを開くカテゴリーを選択してください...", options=select_options)

    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction, int(self.values[0].split('_')[0]))

async def create_ticket(interaction: discord.Interaction, category_id: int, answers=None):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=category_id)
    if not category:
        await interaction.response.send_message("カテゴリーが見つかりません！", ephemeral=True)
        return

    if discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}"):
        await interaction.response.send_message("既にチケットが開かれています！", ephemeral=True)
        return

    staff_role = discord.utils.get(guild.roles, id=settings["staff_role"].get(guild.id))
    allowed_roles = [discord.utils.get(guild.roles, id=role_id) for role_id in settings["allowed_roles"].get(guild.id, [])]

    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    for role in allowed_roles:
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    ticket_channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
    embed_title = settings.get("embed_title", {}).get(guild.id, "チケット")
    description = settings.get("embed_description", {}).get(guild.id, "サポートが必要ですか？")
    color = settings.get("embed_color", {}).get(guild.id, discord.Color.blue())
    image_file = settings["open_image"].get(guild.id)

    if answers:
        description += "\n\n" + "\n.join([f"{key}: {value}" for key, value in answers.items()])

    await interaction.response.send_message(embed=discord.Embed(title="🎫 チケットが作成されました。", description="下のボタンをクリックしてアクセスしてください。", color=color).set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None), view=VisitTicketView(ticket_channel), ephemeral=True)

    files = [await image_file.to_file()] if image_file else []

    embed = discord.Embed(title=embed_title, description=description, color=color).set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None).set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    if files:
        embed.set_image(url=f"attachment://{files[0].filename}")

    await ticket_channel.send(f"{interaction.user.mention} {staff_role.mention if staff_role else ''}", embed=embed, view=CloseTicketView(), files=files)

class VisitTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="チケットに行く", style=discord.ButtonStyle.success, emoji="🎫", url=ticket_channel.jump_url))

class CloseTicketView(discord.ui.View):
    @discord.ui.button(label="Pin チケット", style=discord.ButtonStyle.green, custom_id="pin_ticket", emoji="📌")
    async def pin_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, id=settings["staff_role"].get(interaction.guild.id))
        if staff_role not in interaction.user.roles:
            await interaction.response.send_message("この操作を行う権限がありません。", ephemeral=True)
            return
        await interaction.channel.edit(name=f"📌{interaction.channel.name}")
        await interaction.response.send_message("チケットがピンされました。", ephemeral=True)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="close_ticket", emoji="❎")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=discord.Embed(title="チケットを閉じますか？", description="本当にこのチケットを閉じますか？", color=discord.Color.red()), view=ConfirmCloseView(), ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    @discord.ui.button(label="はい", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        dm_message = settings["dm_message"].get(interaction.guild.id, "")
        ticket_link = settings["link"].get(interaction.guild.id, "")
        image_file = settings["close_image"].get(interaction.guild.id)
        files = [await image_file.to_file()] if image_file else []
        if dm_message:
            embed = discord.Embed(title="📄チケットが閉じました", description=dm_message, color=discord.Color.red()).set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None).add_field(name="作成者", value=f"{interaction.user.mention}\nID: {interaction.user.id}", inline=False).add_field(name="作成日時", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), inline=False).set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            if files:
                embed.set_image(url=f"attachment://{files[0].filename}")
            view = discord.ui.View()
            if ticket_link:
                view.add_item(discord.ui.Button(label="チケットをもう一度作成する", style=discord.ButtonStyle.primary, url=ticket_link))
            await interaction.user.send(embed=embed, view=view, files=files)
        await interaction.channel.delete()

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)

@bot.tree.command(name="ticket_button", description="チケット作成ボタンとスタッフロールを設定します。")
@app_commands.describe(emoji="ボタンに表示する絵文字", name="ボタンの名前", description="ボタンの説明", staff_role="通知するスタッフロール（@メンション）")
async def ticket_button_command(interaction: discord.Interaction, emoji: str, name: str, description: str, staff_role: discord.Role):
    category_options = [discord.SelectOption(label=category.name, value=str(category.id)) for category in interaction.guild.categories]

    class CategorySelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.add_item(CategorySelect())

    class CategorySelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="カテゴリーを選択してください...", options=category_options)

        async def callback(self, interaction: discord.Interaction):
            category_id = int(self.values[0])
            if interaction.guild.id not in settings["ticket"]:
                settings["ticket"][interaction.guild.id] = []

            settings["ticket"][interaction.guild.id].append({"category": category_id, "emoji": emoji, "name": name, "description": description})
            settings["staff_role"][interaction.guild.id] = staff_role.id
            await interaction.response.send_message(f"ボタン '{name}' (カテゴリー: {category_id}, 絵文字: {emoji}) とスタッフロール '{staff_role.name}' を追加しました。", ephemeral=True)

    await interaction.response.send_message("カテゴリーを選択してください：", view=CategorySelectView(), ephemeral=True)

@bot.tree.command(name="ticket_title", description="チケットパネルのタイトルと説明を設定します。")
async def ticket_title_command(interaction: discord.Interaction):
    class TicketModal(discord.ui.Modal, title="チケットパネル設定"):
        title_field = discord.ui.TextInput(label="チケットパネルのタイトルとURL", style=discord.TextStyle.short, placeholder="例: サポートチケット https://example.com", required=True)
        description_field = discord.ui.TextInput(label="チケットパネルの説明", style=discord.TextStyle.paragraph, placeholder="例: サポートチームに連絡したい内容を書いてください。", required=False)

        async def on_submit(self, interaction: discord.Interaction):
            title_url = self.title_field.value.split(' ')
            title, url = title_url[0], title_url[1] if len(title_url) > 1 else ""
            settings["panel_title"][interaction.guild.id], settings["panel_description"][interaction.guild.id], settings["panel_url"][interaction.guild.id] = title, self.description_field.value, url
            await interaction.response.send_message(f"チケットパネルのタイトルを '{title}' に、説明を設定しました。", ephemeral=True)

    await interaction.response.send_modal(TicketModal())

@bot.tree.command(name="open_ticket_settings", description="チケットが送信されたときのEmbedカラー、タイトル、説明を設定します。")
async def open_ticket_settings_command(interaction: discord.Interaction):
    class OpenTicketModal(discord.ui.Modal, title="チケット設定"):
        title_field = discord.ui.TextInput(label="チケットのタイトル", style=discord.TextStyle.short, placeholder="例: サポートチケット", required=True)
        description_field = discord.ui.TextInput(label="チケットの説明", style=discord.TextStyle.paragraph, placeholder="例: サポートチームに連絡したい内容を書いてください。", required=False)
        color_field = discord.ui.TextInput(label="チケットのEmbedカラー（赤、青、黄色、緑から選択）", style=discord.TextStyle.short, placeholder="例: 青", required=True)

        async def on_submit(self, interaction: discord.Interaction):
            color_dict = {"赤": discord.Color.red(), "青": discord.Color.blue(), "黄色": discord.Color.gold(), "緑": discord.Color.green()}
            embed_color = color_dict.get(self.color_field.value, discord.Color.blue())
            settings["embed_title"][interaction.guild.id], settings["embed_description"][interaction.guild.id], settings["embed_color"][interaction.guild.id] = self.title_field.value, self.description_field.value, embed_color
            await interaction.response.send_message("チケットのEmbed設定を保存しました。", ephemeral=True)

    await interaction.response.send_modal(OpenTicketModal())

@bot.tree.command(name="ticket_panel", description="チケットパネルを作成します。")
async def ticket_panel_command(interaction: discord.Interaction):
    buttons = settings["ticket"].get(interaction.guild.id, [])
    if not buttons:
        await interaction.response.send_message("チケットのボタンが設定されていません！", ephemeral=True)
        return

    guild_info = settings["developed_info"].get(interaction.guild.id, {})
    panel_title = settings["panel_title"].get(interaction.guild.id, "チケットサポート")
    panel_description = settings["panel_description"].get(interaction.guild.id, "以下のボタンを押してチケットを開いてください。")
    panel_url = settings["panel_url"].get(interaction.guild.id, "#")

    embed = create_ticket_embed(title=f"[{panel_title}]({panel_url})", description=panel_description, image_file=settings["panel_image"].get(interaction.guild.id), color=settings["panel_color"].get(interaction.guild.id, discord.Color.blue()), top_right_image_file=settings["top_right_image"].get(interaction.guild.id)).set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    if guild_info:
        embed.set_footer(text=guild_info.get("text"), icon_url=guild_info.get("icon_url"))

    await interaction.channel.send(embed=embed, view=TicketView(buttons))
    await interaction.response.send_message("チケットパネルを作成しました。", ephemeral=True)

@bot.tree.command(name="ticket_dm", description="チケットを開いた際にDMで送信する内容を設定します。")
async def ticket_dm_command(interaction: discord.Interaction):
    class DmModal(discord.ui.Modal, title="DMメッセージ設定"):
        message_field = discord.ui.TextInput(label="DMメッセージ", style=discord.TextStyle.paragraph, placeholder="例: チケットが開かれました。ご利用ありがとうございました。", required=True)
        link_field = discord.ui.TextInput(label="チケットリンク", style=discord.TextStyle.short, placeholder="例: https://discord.com/channels/...", required=True)

        async def on_submit(self, interaction: discord.Interaction):
            settings["dm_message"][interaction.guild.id], settings["link"][interaction.guild.id] = self.message_field.value, self.link_field.value
            await interaction.response.send_message("DMメッセージとチケットリンクを設定しました。", ephemeral=True)

    await interaction.response.send_modal(DmModal())

@bot.tree.command(name="ticket_settings", description="チケットパネルの設定を管理します。")
@app_commands.describe(image_file="パネルに表示する画像やGIFのファイル", color="パネルの埋め込みカラー（赤、青、黄色、緑から選択）", top_right_image_file="パネルの右上に表示する画像やGIFのファイル", allowed_roles="チケットを見れるようにするロール（@メンション）")
async def ticket_settings_command(interaction: discord.Interaction, image_file: discord.Attachment, color: str, top_right_image_file: discord.Attachment, allowed_roles: discord.Role):
    color_dict = {"赤": discord.Color.red(), "青": discord.Color.blue(), "黄色": discord.Color.gold(), "緑": discord.Color.green()}
    embed_color = color_dict.get(color, discord.Color.blue())
    settings["panel_image"][interaction.guild.id], settings["panel_color"][interaction.guild.id], settings["top_right_image"][interaction.guild.id], settings["allowed_roles"][interaction.guild.id] = image_file, embed_color, top_right_image_file, allowed_roles.id
    await interaction.response.send_message("チケットパネルの設定を保存しました。", ephemeral=True)

@bot.tree.command(name="ticket_embed_settings", description="チケットを開いた時と閉じた時のembedに画像を追加します。")
@app_commands.describe(open_image_file="チケットを開いた時のembedに表示する画像のファイル", close_image_file="チケットを閉じた時のembedに表示する画像のファイル")
async def ticket_embed_settings_command(interaction: discord.Interaction, open_image_file: discord.Attachment, close_image_file: discord.Attachment):
    settings["open_image"][interaction.guild.id], settings["close_image"][interaction.guild.id] = open_image_file, close_image_file
    await interaction.response.send_message("チケットのembed画像設定を保存しました。", ephemeral=True)

@bot.tree.command(name="ticket_develop", description="チケットパネルの左下に表示する文章と画像を設定します。")
@app_commands.describe(text="表示する文章", icon_url="表示するアイコンのURL")
async def ticket_develop_command(interaction: discord.Interaction, text: str, icon_url: str):
    settings["developed_info"][interaction.guild.id] = {"text": text, "icon_url": icon_url}
    await interaction.response.send_message("チケットパネルの開発者情報を設定しました。", ephemeral=True)

@bot.tree.command(name="ticket_save", description="現在の設定を保存します。")
async def ticket_save_command(interaction: discord.Interaction):
    with open("settings.json", "w") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    await interaction.response.send_message("現在の設定を保存しました。", ephemeral=True)

@bot.tree.command(name="ticket_load", description="保存された設定をロードします。")
async def ticket_load_command(interaction: discord.Interaction):
    global settings
    with open("settings.json", "r") as f:
        settings = json.load(f)
    await interaction.response.send_message("保存された設定をロードしました。", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.attachments:
        for attachment in message.attachments:
            if attachment.url.lower().endswith(('png', 'jpg', 'jpeg', 'gif')):
                await message.channel.send(f"画像/ファイルのURLを取得しました: {attachment.url}")

bot.run("YOUR_BOT_TOKEN")