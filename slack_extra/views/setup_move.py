from blockkit import Modal
from blockkit import Section
from slack_bolt.async_app import AsyncAck
from slack_sdk.web.async_client import AsyncWebClient

from slack_extra.tables import MigrationChannel
from slack_extra.tables import MigrationConfig
from slack_extra.utils.logging import send_heartbeat
from slack_extra.utils.slack import is_channel_manager


async def setup_move_handler(ack: AsyncAck, body: dict, client: AsyncWebClient):
    user_id = body["user"]["id"]
    view = body["view"]
    values = view["state"]["values"]
    name = values["name"]["name"]["value"]
    channels = values["channels"]["channels"]["selected_channels"]
    one_way_channels = values["one_way_channels"]["one_way_channels"].get(
        "selected_channels", []
    )
    private_metadata = view["private_metadata"]
    editing = True if "edit" in private_metadata else False
    await send_heartbeat(f"{private_metadata.split(':')[-1]}")
    config_val = int(private_metadata.split(":")[-1]) if editing else None

    both = [c for c in one_way_channels if c in channels]
    if both:
        both_channels = ", ".join([f"<#{c}>" for c in both])
        return await ack(
            response_action="errors",
            errors={
                "one_way_channels": f"These channels can't be both two-way and one-way: {both_channels}"
            },
        )

    all_channels = channels + one_way_channels
    blocks = {"channels": channels, "one_way_channels": one_way_channels}

    errors = {}
    for block_id, block_channels in blocks.items():
        allowed = [await is_channel_manager(user_id, c) for c in block_channels]
        if not all(allowed):
            errors[block_id] = (
                "You must be a channel manager of all selected channels to set up migrations."
            )

    if errors:
        return await ack(response_action="errors", errors=errors)

    for block_id, block_channels in blocks.items():
        exist = []
        for c in block_channels:
            db_channel = (
                await MigrationChannel.objects()
                .where(MigrationChannel.channel_id == c)
                .first()
            )
            if db_channel and db_channel.config != config_val:
                exist.append(c)

        if exist:
            existing_channels = ", ".join([f"<#{c}>" for c in exist])
            errors[block_id] = (
                f"These channels are already configured for migration: {existing_channels}"
            )

    if errors:
        return await ack(response_action="errors", errors=errors)

    for c in all_channels:
        try:
            await client.conversations_join(channel=c)
        except Exception as e:
            await send_heartbeat(f"Error joining channel {c} for user {user_id}: {e}")
            block_id = "one_way_channels" if c in one_way_channels else "channels"
            return await ack(
                response_action="errors",
                errors={
                    block_id: f"An unexpected error occurred while joining <#{c}>. Please ensure the bot is invited to the channel and try again."
                },
            )

    try:
        async with MigrationConfig._meta.db.transaction():
            if editing:
                await MigrationConfig.update({MigrationConfig.name: name}).where(
                    MigrationConfig.id == config_val
                )
                config_id = config_val

                existing_channels = await MigrationChannel.select(
                    MigrationChannel.channel_id
                ).where(MigrationChannel.config == config_id)
                existing_channel_ids = {c["channel_id"] for c in existing_channels}

                channels_to_delete = existing_channel_ids - set(all_channels)
                if channels_to_delete:
                    await MigrationChannel.delete().where(
                        MigrationChannel.config == config_id,
                        MigrationChannel.channel_id.is_in(list(channels_to_delete)),
                    )

                await MigrationChannel.update({MigrationChannel.one_way: False}).where(
                    MigrationChannel.config == config_id,
                    MigrationChannel.channel_id.is_in(channels),
                )
                if one_way_channels:
                    await MigrationChannel.update(
                        {MigrationChannel.one_way: True}
                    ).where(
                        MigrationChannel.config == config_id,
                        MigrationChannel.channel_id.is_in(one_way_channels),
                    )

                channels_to_add = set(all_channels) - existing_channel_ids
            else:
                conf = await MigrationConfig.insert(
                    MigrationConfig(name=name, user_id=user_id)
                ).returning(MigrationConfig.id)
                config_id = conf[0]["id"]
                channels_to_add = all_channels

            if channels_to_add:
                migration_channels = [
                    MigrationChannel(
                        channel_id=c, config=config_id, one_way=c in one_way_channels
                    )
                    for c in channels_to_add
                ]
                await MigrationChannel.insert(*migration_channels)
    except Exception as e:
        await send_heartbeat(f"Error setting up migration for user {user_id}: {e}")
        return await ack(
            response_action="errors",
            errors={
                "name": "An unexpected error occurred while setting up the migration. Please try again later."
            },
        )

    action = "Updated" if editing else "Setup"
    view = (
        Modal()
        .title(f"Migration {action}!")
        .add_block(
            Section(text=f"Your migration has been {action.lower()} successfully :D")
        )
        .close("Yippee!")
    ).build()
    await ack(response_action="update", view=view)
