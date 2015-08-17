def welcome_message():
    import random
    from pymc.util import chat
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
    import pymc.network.connection
    from pymc.util import event

    @event.handler(pymc.network.connection.ping_event)
    def ping_handler(data):
        print "Handling ping!"
        data.description = welcome_message()

    import pymc.network.server
    pymc.network.server.start("0.0.0.0", 25565)
