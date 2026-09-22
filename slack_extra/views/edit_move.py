from blockkit import ConversationFilter
from blockkit import Input
from blockkit import Modal
from blockkit import MultiConversationsSelect
from blockkit import PlainTextInput
from blockkit import Section
from slack_bolt.async_app import AsyncAck
from slack_sdk.web.async_client import AsyncWebClient

from slack_extra.config import config
from slack_extra.tables import MigrationChannel
from slack_extra.tables import MigrationConfig
from slack_extra.utils.error import generate_error_view


async def edit_move_handler(ack: AsyncAck, body: dict, client: AsyncWebClient):
    view = body["view"]
    values = view["state"]["values"]
    config_val = int(values["config"]["config"]["selected_option"]["value"])

    migration = (
        await MigrationConfig.objects().where(MigrationConfig.id == config_val).first()
    )

    if not migration:
        view = generate_error_view(
            "No config found",
            f"We couldn't find your config! If you keep running into this, please post in {config.slack.support_channel}",
        )
        return await ack(response_action="update", view=view)

    channels = await MigrationChannel.objects().where(
        MigrationChannel.config == config_val
    )
    channels_list = [c.channel_id for c in channels if not c.one_way]
    one_way_channels_list = [c.channel_id for c in channels if c.one_way]

    one_way_select = (
        MultiConversationsSelect()
        .action_id("one_way_channels")
        .filter(ConversationFilter().include(["public", "private"]))
        .placeholder("Select channels")
    )
    for c in one_way_channels_list:
        one_way_select.add_initial_conversation(c)

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
            .element(PlainTextInput().action_id("name").initial_value(migration.name))
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
                .initial_conversations(*channels_list)
            )
            .block_id("channels")
        )
        .add_block(
            Input()
            .label("One-way channels")
            .element(one_way_select)
            .block_id("one_way_channels")
            .optional()
        )
        .private_metadata(f"edit:{config_val}")
        .submit("Update!")
        .close("Cancel")
    ).build()

    return await ack(response_action="push", view=view)
