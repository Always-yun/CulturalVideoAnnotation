"""Deterministic entity-name normalization, without feature-keyword credit."""
import re


# Grammatical/visual presentation qualifiers, never a second proper entity.
# Longest-first matching prevents an earlier short alternative swallowing text.
QUALIFIERS = ('建筑群', '天际线', '城市景观', '现代建筑群', '传统建筑群',
              '园区', '校园', '景区', '校门', '大门', '正门', '西门', '东门',
              '南门', '北门', '全景', '外观', '主体', '建筑', '区域', '街景',
              '夜景', '航拍', '景观', '的')
TAIL = re.compile('(?:' + '|'.join(sorted(QUALIFIERS, key=len, reverse=True)) + ')*$')


def normalize(value):
    return re.sub(r'[\s“”\"\[\]。]', '', str(value)).lower()


def asserted_names(core):
    """Split entity list before removing each item's explanatory parentheses."""
    text = str(core).strip()
    if '为' in text:
        text = text.split('为', 1)[1]
    text = text.split('。', 1)[0]
    pieces, current, depth = [], [], 0
    for c in text:
        if c in '（(':
            depth += 1
        elif c in '）)':
            depth = max(0, depth - 1)
        if c in '、，,；;' and depth == 0:
            pieces.append(''.join(current)); current = []
        else:
            current.append(c)
    pieces.append(''.join(current))
    return [normalize(re.sub(r'（[^（）]*）|\([^()]*\)', '', p)) for p in pieces if normalize(p)]


def entity_matches(name, target, kb):
    symbol = kb.get_by_name(target)
    aliases = [target]
    region = ''
    if symbol:
        aliases += [symbol['canonical_name']] + str(symbol.get('aliases', '')).split('|')
        region = normalize(symbol.get('region', ''))
    forms = [name]
    if region and name.startswith(region):
        forms.append(name[len(region):])
    for form in forms:
        for alias in aliases:
            alias = normalize(alias)
            if alias and form.startswith(alias) and TAIL.fullmatch(form[len(alias):]):
                return True
    return False


def final_entity_correct(core, unknown, targets, kb):
    names = asserted_names(core)
    return bool(names and not unknown and all(any(entity_matches(n, g, kb) for g in targets) for n in names))
