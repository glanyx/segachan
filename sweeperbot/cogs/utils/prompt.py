import asyncio


class Prompt:
    def __init__(self, bot):
        self.bot = bot
        self.ctx = None

    async def send(
        self, ctx, message, *, timeout=60.0, delete_after=True, author_id=None
    ):
        """An interactive reaction confirmation dialog.
        Parameters
        -----------
        ctx: context
            The context message involved.
        message: str
            The message to show along with the prompt.
        timeout: float
            How long to wait before returning.
        delete_after: bool
            Whether to delete the confirmation message after we're done.
        author_id: Optional[int]
            The member who should respond to the prompt. Defaults to the author of the
            Context's message.
        Returns
        --------
        Optional[bool]
            ``True`` if explicit confirm,
            ``False`` if explicit deny,
            ``None`` if deny due to timeout
        """

        self.ctx = ctx

        if not self.ctx.channel.permissions_for(self.ctx.me).add_reactions:
            raise RuntimeError("Bot does not have Add Reactions permission.")

        fmt = f"{message}\n\nReact with \N{WHITE HEAVY CHECK MARK} to confirm or \N{CROSS MARK} to deny within {timeout} seconds."

        author_id = author_id or self.ctx.author.id
        msg = await self.ctx.send(fmt)

        confirm = None

        def check(payload):
            nonlocal confirm

            if payload.message_id != msg.id or payload.user_id != author_id:
                return False

            codepoint = str(payload.emoji)

            if codepoint == "\N{WHITE HEAVY CHECK MARK}":
                confirm = True
                return True
            elif codepoint == "\N{CROSS MARK}":
                confirm = False
                return True

            return False

        for emoji in ("\N{WHITE HEAVY CHECK MARK}", "\N{CROSS MARK}"):
            await msg.add_reaction(emoji)

        try:
            await self.bot.wait_for("raw_reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            confirm = None

        try:
            if delete_after:
                await msg.delete()
        finally:
            return confirm
