from schema import Schema, And, Or, Optional

# used for python2 and python3 string types
from six import text_type

def is_stringy(v):
    return type(v) is text_type

TemplateSchema = Schema({
    "args": [is_stringy],
    Optional("run_type", default="composite"): And(is_stringy, lambda rt: rt.lower() in ["multi", "composite", "distributed_ctrl_txl", "distributed_sut"]),
    Optional("java", default="java"): is_stringy,
    Optional("jar", default="specjbb2015.jar"): is_stringy,
    Optional("default_props"): {
        is_stringy: object,
        },
    Optional("annotations"): {
        is_stringy: is_stringy,
        },
    Optional("translations"): {
        is_stringy: is_stringy,
        },
    Optional("types"): {
        is_stringy: is_stringy,
        },
    })

RunConfigSchema = Schema({
    "template_type": is_stringy,
    "args": {
        Optional(is_stringy): object,
        },
    Optional("props_extra"): {
        Optional(is_stringy): is_stringy,
        },
    })

SpectateConfig = Schema({
    "TemplateData": { 
        is_stringy: TemplateSchema,
    },
    "RunList": [RunConfigSchema],
    })

def validate(unvalidated):
    d = SpectateConfig.validate(unvalidated)

    # each of the args that appear in the RunList,
    for run in d["RunList"]:
        # for the TemplateData they pull from,
        t = d["TemplateData"][run["template_type"]]

        # they need to appear in the template
        for arg in run["args"]:
            if arg not in t["args"]:
                return None

        # and if the arg isn't in the run,
        # it needs to have a default
        for arg in t["args"]:
            if arg not in run["args"] and arg not in t["default_props"]:
                return None

    # for each template,
    for template in d["TemplateData"].values():
        # all of the translations need to refer to
        # arguments specified by the user
        if "translations" in template:
            for translation in template["translations"]:
                if translation not in template["args"]:
                    return None
        # all of the annotations need to refer to
        # arguments specified by the user
        if "annotations" in template:
            for annotation in template["annotations"]:
                if annotation not in template["args"]:
                    return None

    return d