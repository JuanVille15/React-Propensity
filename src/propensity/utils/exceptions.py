'''Define excepciones propias del proyecto'''

class LabelQueryError(Exception):
    pass

class FeatureQueryError(Exception):
    pass

class DuplicateFeatureError(Exception):
    pass

class FeatureNoMatchError(Exception):
    pass