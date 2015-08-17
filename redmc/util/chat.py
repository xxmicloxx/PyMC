class MessageBuilder(object):
    def __init__(self):
        self.elements = []
    
    def append(self, message):
        self.elements.append(message)
        return self
        
    def encode(self):
        if len(self.elements) == 0:
            return {"text": ""}
        
        first_dic = self.elements[0].encode()
        current_dic = first_dic
        for i in range(len(self.elements)):
            if i == 0:
                continue
            
            temp_dic = self.elements[i].encode()
            current_dic.update({"extra": [temp_dic]})
            current_dic = temp_dic
        
        return first_dic


class BaseElement(object):
    def __init__(self):
        super(BaseElement, self).__init__()
    
    def encode(self):
        raise NotImplementedError()


class MessageElement(BaseElement):
    def __init__(self):
        super(MessageElement, self).__init__()
        self.color = None
        self.bold = None
        self.italic = None
        self.underlined = None
        self.strikethrough = None
        self.obfuscated = None
        self.hover_event = None
        self.click_event = None
    
    def encode(self):
        dic = {}
        
        elements = ["color", "bold", "italic", "underlined", "strikethrough", "obfuscated"]
        for elem in elements:
            attr = getattr(self, elem)
            if attr is not None:
                dic.update({elem: attr})
        
        if self.hover_event is not None:
            dic.update({"hoverEvent": self.hover_event.encode()})
        
        if self.click_event is not None:
            dic.update({"clickEvent": self.click_event.encode()})
        
        return dic


class TextElement(MessageElement):
    def __init__(self, text = ""):
        super(TextElement, self).__init__()
        self.text = text
    
    def encode(self):
        dic = super(TextElement, self).encode()
        dic.update({"text": self.text})
        return dic
