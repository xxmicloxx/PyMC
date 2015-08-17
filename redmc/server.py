def welcome_message():
    import random
    from redmc.util import chat
    message_builder = chat.MessageBuilder()

    element = chat.TextElement("I can haz ")
    message_builder.append(element)

    colorz = ["yellow", "gold", "aqua", "blue", "light_purple", "red", "green"]

    text = "colorz!"
    for char in text:
        element = chat.TextElement(char)
        element.italic = True
        element.color = random.choice(colorz)
        colorz.remove(element.color)
        message_builder.append(element)

    return message_builder.encode()


def start():
    import redmc.network.connection
    from redmc.util import event

    @event.handler(redmc.network.connection.ping_event)
    def ping_handler(data):
        print "Handling ping!"
        data.description = welcome_message()

    @event.handler(redmc.network.connection.pre_connect_event)
    def pre_connect_handler(data):
        if data.player_name == "xxmicloxx":
            data.cancelled = True
            data.cancel_reason = welcome_message()

    import redmc.network.server
    redmc.network.server.start("0.0.0.0", 25565)
