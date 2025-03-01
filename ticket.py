import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import json
import os

# Ensure the save directory exists
SAVE_DIR = "ticket_saves"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# Intentsの設定
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True  # メッセージ内容へのアクセスを許可

# Botインスタンスの作成
bot = commands.Bot(command_prefix="/", intents=intents)

# チケット用の設定を保持する辞書（既存機能は変更せずに保持）
settings = {
    "ticket": {},
    "panel_title": {},
    "panel_description": {},
    "panel_url": {},
    "staff_role": {},
    "developed_info": {},
    "dm_message": {},
    "embed_title": {},
    "embed_description": {},
    "embed_color": {},
    "link": {},
    "panel_image": {},
    "panel_color": {},
    "top_right_image": {},
    "developer_text": {},
    "developer_image": {},
    "open_image": {},
    "close_image": {},
}

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
        # optionsは settings["ticket"][guild_id] のリスト
        select_options = [
            discord.SelectOption(
                label=option["name"],
                value=f"{option['category']}_{index}",
                description=option["description"],
                emoji=option["emoji"]
            )
            for index, option in enumerate(options)
        ]
        super().__init__(placeholder="チケットを開くカテゴリーを選択してください...", options=select_options)

    async def callback(self, interaction: discord.Interaction):
        # 選択されたオプションのindexを取得し、対応するbutton_configを取り出す
        index = int(self.values[0].split('_')[1])
        button_config = settings["ticket"][interaction.guild.id][index]
        category_id = int(button_config["category"])
        await create_ticket(interaction, category_id, button_config)

async def create_ticket(interaction: discord.Interaction, category_id: int, button_config: dict, answers=None):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=category_id)
    if not category:
        await interaction.response.send_message("カテゴリーが見つかりません！", ephemeral=True)
        return

    if discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}"):
        await interaction.response.send_message("既にチケットが開かれています！", ephemeral=True)
        return

    # チケット作成時に通知するスタッフロールの取得
    staff_role = discord.utils.get(guild.roles, id=settings["staff_role"].get(guild.id))

    # 追加：ボタンごとに指定されたticket_roleがあれば取得する
    ticket_role = None
    if "ticket_role" in button_config and button_config["ticket_role"]:
        ticket_role = guild.get_role(button_config["ticket_role"])

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    # ticket_roleにも閲覧権限を付与
    if ticket_role:
        overwrites[ticket_role] = discord.PermissionOverwrite(read_messages=True)

    ticket_channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites
    )

    embed_title = settings.get("embed_title", {}).get(guild.id, "チケット")
    description = settings.get("embed_description", {}).get(guild.id, "サポートが必要ですか？")
    color = settings.get("embed_color", {}).get(guild.id, discord.Color.blue())

    # Get the open image URL correctly whether stored as attachment or URL string.
    open_image_setting = settings["open_image"].get(guild.id)
    if open_image_setting:
        if hasattr(open_image_setting, "url"):
            image_url = open_image_setting.url
        elif isinstance(open_image_setting, str):
            image_url = open_image_setting
        else:
            image_url = None
    else:
        image_url = None

    if answers:
        description += "\n\n" + "\n".join([f"{key}: {value}" for key, value in answers.items()])

    await interaction.response.send_message(
        embed=discord.Embed(
            title="🎫 チケットが作成されました。",
            description="下のボタンをクリックしてアクセスしてください。",
            color=color
        ).set_author(
            name=interaction.user.name,
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        ),
        view=VisitTicketView(ticket_channel),
        ephemeral=True,
    )

    embed = discord.Embed(
        title=embed_title,
        description=description,
        color=color
    ).set_author(
        name=guild.name, icon_url=guild.icon.url if guild.icon else None
    ).set_thumbnail(
        url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    if image_url:
        embed.set_image(url=image_url)

    await ticket_channel.send(
        f"{interaction.user.mention} {staff_role.mention if staff_role else ''}",
        embed=embed,
        view=CloseTicketView()
    )

class VisitTicketView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="チケットに行く",
            style=discord.ButtonStyle.success,
            emoji="🎫",
            url=ticket_channel.jump_url
        ))

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
        embed = discord.Embed(
            title="チケットを閉じますか？",
            description="本当にこのチケットを閉じますか？",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=ConfirmCloseView(), ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    @discord.ui.button(label="はい", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        dm_message = settings["dm_message"].get(interaction.guild.id, "")
        ticket_link = settings["link"].get(interaction.guild.id, "")
        image_file = settings["close_image"].get(interaction.guild.id)
        if dm_message:
            embed = discord.Embed(
                title="📄チケットが閉じました", description=dm_message, color=discord.Color.red()
            ).set_author(
                name=interaction.guild.name,
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            ).add_field(
                name="作成者", value=f"{interaction.user.mention}\nID: {interaction.user.id}", inline=False
            ).add_field(
                name="作成日時", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), inline=False
            ).set_thumbnail(
                url=interaction.user.avatar.url if interaction.user.avatar else None
            )
            if image_file:
                if hasattr(image_file, "url"):
                    embed.set_image(url=image_file.url)
                elif isinstance(image_file, str):
                    embed.set_image(url=image_file)
            view = discord.ui.View()
            if ticket_link:
                view.add_item(discord.ui.Button(
                    label="チケットをもう一度作成する",
                    style=discord.ButtonStyle.primary,
                    url=ticket_link
                ))
            await interaction.user.send(embed=embed, view=view)
        await interaction.channel.delete()

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)

@bot.tree.command(name="ticket_button", description="チケット作成ボタンとスタッフロールおよび閲覧可能ロールを設定します。")
@app_commands.describe(
    emoji="ボタンに表示する絵文字",
    name="ボタンの名前",
    description="ボタンの説明",
    staff_role="通知するスタッフロール（@メンション）",
    ticket_role="チケットを閲覧できる追加ロール（@メンション）"
)
async def ticket_button_command(interaction: discord.Interaction, emoji: str, name: str, description: str, staff_role: discord.Role, ticket_role: discord.Role):
    category_options = [discord.SelectOption(label=category.name, value=str(category.id))
                        for category in interaction.guild.categories]

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
            # ボタンごとの設定情報にticket_roleも追加する
            settings["ticket"][interaction.guild.id].append(
                {
                    "category": category_id,
                    "emoji": emoji,
                    "name": name,
                    "description": description,
                    "ticket_role": ticket_role.id
                }
            )
            settings["staff_role"][interaction.guild.id] = staff_role.id
            await interaction.response.send_message(
                f"ボタン '{name}' (カテゴリー: {category_id}, 絵文字: {emoji}) とスタッフロール '{staff_role.name}'、閲覧可能ロール '{ticket_role.name}' を追加しました。",
                ephemeral=True,
            )

    await interaction.response.send_message("カテゴリーを選択してください：", view=CategorySelectView(), ephemeral=True)

@bot.tree.command(name="ticket_title", description="チケットパネルのタイトルと説明を設定します。")
async def ticket_title_command(interaction: discord.Interaction):
    class TicketModal(discord.ui.Modal, title="チケットパネル設定"):
        title_field = discord.ui.TextInput(
            label="チケットパネルのタイトル",
            style=discord.TextStyle.short,
            placeholder="例: サポートチケット",
            required=True,
        )
        description_field = discord.ui.TextInput(
            label="チケットパネルの説明",
            style=discord.TextStyle.paragraph,
            placeholder="例: サポートチームに連絡したい内容を書いてください。",
            required=False,
        )
        title_url_field = discord.ui.TextInput(
            label="タイトルのURL",
            style=discord.TextStyle.short,
            placeholder="例: https://example.com",
            required=False,
        )

        async def on_submit(self, interaction: discord.Interaction):
            title = self.title_field.value
            title_url = self.title_url_field.value
            if title_url:
                settings["panel_title"][interaction.guild.id] = title
                settings["panel_url"][interaction.guild.id] = title_url
            else:
                settings["panel_title"][interaction.guild.id] = title
                settings["panel_url"][interaction.guild.id] = None
            settings["panel_description"][interaction.guild.id] = self.description_field.value
            await interaction.response.send_message(
                f"チケットパネルのタイトルを '{self.title_field.value}' に、説明を設定しました。",
                ephemeral=True
            )
    await interaction.response.send_modal(TicketModal())

@bot.tree.command(name="open_ticket_settings", description="チケットが送信されたときのEmbedカラー、タイトル、説明を設定します。")
async def open_ticket_settings_command(interaction: discord.Interaction):
    class OpenTicketModal(discord.ui.Modal, title="チケット設定"):
        title_field = discord.ui.TextInput(
            label="チケットのタイトル",
            style=discord.TextStyle.short,
            placeholder="例: サポートチケット",
            required=True,
        )
        description_field = discord.ui.TextInput(
            label="チケットの説明",
            style=discord.TextStyle.paragraph,
            placeholder="例: サポートチームに連絡したい内容を書いてください。",
            required=False,
        )
        color_field = discord.ui.TextInput(
            label="チケットのEmbedカラー（赤、青、黄色、緑から選択）",
            style=discord.TextStyle.short,
            placeholder="例: 青",
            required=True,
        )

        async def on_submit(self, interaction: discord.Interaction):
            color_dict = {
                "赤": discord.Color.red(),
                "青": discord.Color.blue(),
                "黄色": discord.Color.gold(),
                "緑": discord.Color.green()
            }
            embed_color = color_dict.get(self.color_field.value, discord.Color.blue())
            settings["embed_title"][interaction.guild.id] = self.title_field.value
            settings["embed_description"][interaction.guild.id] = self.description_field.value
            settings["embed_color"][interaction.guild.id] = embed_color
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
    panel_url = settings["panel_url"].get(interaction.guild.id)
    if panel_url:
        embed = discord.Embed(
            title=panel_title,
            url=panel_url,
            description=panel_description,
            color=settings["panel_color"].get(interaction.guild.id, discord.Color.blue())
        )
    else:
        embed = discord.Embed(
            title=panel_title,
            description=panel_description,
            color=settings["panel_color"].get(interaction.guild.id, discord.Color.blue())
        )
    embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    if guild_info:
        embed.set_footer(text=guild_info.get("text"), icon_url=guild_info.get("icon_url"))
    # Check if panel_image is stored as an attachment or a URL string
    if settings["panel_image"].get(interaction.guild.id):
        image_obj = settings["panel_image"][interaction.guild.id]
        if hasattr(image_obj, "filename"):
            embed.set_image(url=f"attachment://{image_obj.filename}")
        else:
            embed.set_image(url=image_obj)
    view = TicketView(buttons)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("チケットパネルを作成しました。", ephemeral=True)

@bot.tree.command(name="ticket_dm", description="チケットを開いた際にDMで送信する内容を設定します。")
async def ticket_dm_command(interaction: discord.Interaction):
    class DmModal(discord.ui.Modal, title="DMメッセージ設定"):
        message_field = discord.ui.TextInput(
            label="DMメッセージ",
            style=discord.TextStyle.paragraph,
            placeholder="例: チケットが開かれました。ご利用ありがとうございました。",
            required=True,
        )
        link_field = discord.ui.TextInput(
            label="チケットリンク",
            style=discord.TextStyle.short,
            placeholder="例: https://discord.com/channels/...",
            required=True,
        )
        async def on_submit(self, interaction: discord.Interaction):
            settings["dm_message"][interaction.guild.id] = self.message_field.value
            settings["link"][interaction.guild.id] = self.link_field.value
            await interaction.response.send_message("DMメッセージとチケットリンクを設定しました。", ephemeral=True)
    await interaction.response.send_modal(DmModal())

@bot.tree.command(name="ticket_settings", description="チケットパネルの設定を管理します。")
@app_commands.describe(
    image_file="パネルに表示する画像やGIFのファイル",
    color="パネルの埋め込みカラー（赤、青、黄色、緑から選択）",
    top_right_image_file="パネルの右上に表示する画像のファイル"
)
async def ticket_settings_command(interaction: discord.Interaction, image_file: discord.Attachment, color: str, top_right_image_file: discord.Attachment):
    color_dict = {
        "赤": discord.Color.red(),
        "青": discord.Color.blue(),
        "黄色": discord.Color.gold(),
        "緑": discord.Color.green()
    }
    embed_color = color_dict.get(color, discord.Color.blue())
    settings["panel_image"][interaction.guild.id] = image_file
    settings["panel_color"][interaction.guild.id] = embed_color
    settings["top_right_image"][interaction.guild.id] = top_right_image_file
    await interaction.response.send_message("チケットパネルの設定を保存しました。", ephemeral=True)

@bot.tree.command(name="ticket_embed_settings", description="チケットを開いた時と閉じた時のembedに画像を追加します。")
@app_commands.describe(
    open_image_file="チケットを開いた時のembedに表示する画像のファイル",
    close_image_file="チケットを閉じた時のembedに表示する画像のファイル"
)
async def ticket_embed_settings_command(interaction: discord.Interaction, open_image_file: discord.Attachment, close_image_file: discord.Attachment):
    settings["open_image"][interaction.guild.id] = open_image_file
    settings["close_image"][interaction.guild.id] = close_image_file
    await interaction.response.send_message("チケットのembed画像設定を保存しました。", ephemeral=True)

@bot.tree.command(name="ticket_develop", description="チケットパネルの左下に表示する文章と画像を設定します。")
@app_commands.describe(
    text="表示する文章",
    icon_url="表示するアイコンのURL"
)
async def ticket_develop_command(interaction: discord.Interaction, text: str, icon_url: str):
    settings["developed_info"][interaction.guild.id] = {"text": text, "icon_url": icon_url}
    await interaction.response.send_message("チケットパネルの開発者情報を設定しました。", ephemeral=True)

@bot.tree.command(name="ticket_save", description="全ての設定した内容を保存します。")
async def ticket_save_command(interaction: discord.Interaction):
    def serialize_settings():
        serialized = {}
        for key, data in settings.items():
            if isinstance(data, dict):
                serialized[key] = {}
                for guild_id, value in data.items():
                    # Convert discord.Color to its integer value
                    if isinstance(value, discord.Color):
                        serialized[key][guild_id] = value.value
                    # For attachments, store the URL if available
                    elif hasattr(value, "url"):
                        serialized[key][guild_id] = value.url
                    else:
                        serialized[key][guild_id] = value
            else:
                serialized[key] = data
        return serialized

    data = serialize_settings()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(SAVE_DIR, f"ticket_save_{timestamp}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    await interaction.response.send_message(f"設定内容を保存しました。 (File: {os.path.basename(filename)})", ephemeral=True)

class SaveSelect(discord.ui.Select):
    def __init__(self, files):
        options = [
            discord.SelectOption(label=filename, value=filename)
            for filename in files
        ]
        super().__init__(placeholder="ロードする保存ファイルを選択してください...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_file = self.values[0]
        filepath = os.path.join(SAVE_DIR, selected_file)
        if not os.path.exists(filepath):
            await interaction.response.send_message("選択されたファイルが見つかりません。", ephemeral=True)
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        def load_settings_from_data(data):
            for key, guild_data in data.items():
                if isinstance(guild_data, dict):
                    if key not in settings:
                        settings[key] = {}
                    for guild_id_str, value in guild_data.items():
                        guild_id = int(guild_id_str)
                        if key == "embed_color":
                            settings[key][guild_id] = discord.Color(value)
                        else:
                            settings[key][guild_id] = value
                else:
                    settings[key] = guild_data

        load_settings_from_data(data)
        await interaction.response.send_message(f"{selected_file} から設定をロードしました。", ephemeral=True)

class RoadSelectView(discord.ui.View):
    def __init__(self, files):
        super().__init__(timeout=30)
        self.add_item(SaveSelect(files))

@bot.tree.command(name="ticket_road", description="保存済みの設定ファイルを一覧から選んでロードします。")
async def ticket_road_command(interaction: discord.Interaction):
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".json")]
    if not files:
        await interaction.response.send_message("保存された設定ファイルが見つかりません。", ephemeral=True)
        return
    view = RoadSelectView(files)
    await interaction.response.send_message("ロードするファイルを選んでください：", view=view, ephemeral=True)

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
    await bot.process_commands(message)

bot.run("YOUR_BOT_TOKEN")