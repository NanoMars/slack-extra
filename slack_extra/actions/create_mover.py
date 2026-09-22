from blockkit import ConversationFilter
from blockkit import Input
from blockkit import Modal
from blockkit import MultiConversationsSelect
from blockkit import PlainTextInput
from blockkit import Section
from slack_bolt.async_app import AsyncAck
from slack_bolt.async_app import AsyncRespond
from slack_sdk.web.async_client import AsyncWebClient


async def create_mover_handler(
    ack: AsyncAck, client: AsyncWebClient, respond: AsyncRespond, body: dict
):
    await ack()

    view = (
        Modal()
        .callback_id("setup_move")
        .title("Setup Mover")
        .add_block(
            Section(
                text="Users who join any of the two-way channels will be added to all of the two-way channels, as well as all of the one-way channels.\n\nUsers who join any of the one-way channels will not automatically be added to the two-way channels."
            )
        )
        .add_block(
            Input()
            .label("Name")
            .element(PlainTextInput().action_id("name").max_length(71))
            .block_id("name")
        )
        .add_block(
            Input()
            .label("Two-way channels")
            .element(
                MultiConversationsSelect()
                .action_id("channels")
                .filter(ConversationFilter().include(["public", "private"]))
                .placeholder("Select channels")
            )
            .block_id("channels")
        )
        .add_block(
            Input()
            .label("One-way channels")
            .element(
                MultiConversationsSelect()
                .action_id("one_way_channels")
                .filter(ConversationFilter().include(["public", "private"]))
                .placeholder("Select channels")
            )
            .block_id("one_way_channels")
            .optional()
        )
        .private_metadata("create")
        .submit("Setup!")
        .close("Cancel")
    ).build()

    await client.views_push(view=view, trigger_id=body["trigger_id"])
