package business

import (
	"regexp"
	"strings"
)

// A number followed by a power/energy unit, as the client wrote it.
// кВт·ч / кВтч / кВт*ч / кВт ч are energy (consumption), not power.
// Thousands may be grouped with spaces: «1 000 000 кВт·ч».
var powerPattern = regexp.MustCompile(`(?i)(\d{1,3}(?:[ \x{00A0}]\d{3})+|\d+(?:[.,]\d+)?)\s*(квт\s*[·*.]?\s*ч|квтч|мвт|квт)(?:[^а-яё]|$)`)

// Kind words are taken only from the same client sentence; otherwise the kind stays unknown.
var (
	connectedWords   = regexp.MustCompile(`(?i)присоедин|разрешенн|разрешённ|максимальн`)
	consumptionWords = regexp.MustCompile(`(?i)в месяц|в год|в сутки|потребля|потреблени|расход`)
)

func extractPower(text string) []Power {
	out := []Power{}
	lower := strings.ToLower(strings.ReplaceAll(text, "ё", "е"))
	for _, m := range powerPattern.FindAllStringSubmatch(lower, -1) {
		amount := strings.NewReplacer(",", ".", " ", "", " ", "").Replace(m[1])
		unit := strings.ReplaceAll(m[2], " ", "")
		p := Power{Amount: amount}
		switch {
		case strings.HasPrefix(unit, "мвт"):
			p.Unit = "МВт"
		case strings.HasSuffix(unit, "ч"):
			p.Unit = "кВт·ч"
		default:
			p.Unit = "кВт"
		}
		switch {
		case p.Unit == "кВт·ч":
			p.Kind = Field{Value: "потребление", Status: Confirmed, Origin: OriginRule}
		case connectedWords.MatchString(lower):
			p.Kind = Field{Value: "присоединённая", Status: Confirmed, Origin: OriginRule}
		case consumptionWords.MatchString(lower):
			p.Kind = Field{Value: "потребление", Status: Confirmed, Origin: OriginRule}
		default:
			p.Kind = Field{Status: Unknown, Origin: OriginRule}
		}
		out = append(out, p)
	}
	return out
}

func authoritative(o Origin) bool {
	return o == OriginForm || o == OriginClientEdit || o == OriginManager
}

func powerClass(unit string) string {
	if unit == "кВт·ч" {
		return "energy"
	}
	return "power"
}

// resolvePower sets the state of every value within its class (power vs energy):
// confirmed (form/edit) values are actual and the rest become history; with no
// confirmed value a single value is actual and several are unconfirmed.
// Two different values are never actual at the same time unless the client confirmed both.
func resolvePower(list []Power) {
	for _, class := range []string{"power", "energy"} {
		idx, confirmed := []int{}, 0
		for i, p := range list {
			if powerClass(p.Unit) == class {
				idx = append(idx, i)
				if authoritative(p.Origin) {
					confirmed++
				}
			}
		}
		for _, i := range idx {
			switch {
			case confirmed > 0 && authoritative(list[i].Origin):
				list[i].State = PowerActual
			case confirmed > 0:
				list[i].State = PowerHistory
			case len(idx) == 1:
				list[i].State = PowerActual
			default:
				list[i].State = PowerUnconfirmed
			}
		}
	}
}

// appendPower merges repeated mentions of the same value and unit, keeping all evidence,
// a stated kind over an unknown one and the most authoritative origin.
func appendPower(list []Power, p Power) []Power {
	for i := range list {
		if list[i].Amount == p.Amount && list[i].Unit == p.Unit {
			if list[i].Kind.Status == Unknown && p.Kind.Status != Unknown {
				list[i].Kind = p.Kind
			}
			if authoritative(p.Origin) && !authoritative(list[i].Origin) {
				list[i].Origin = p.Origin
			}
			for _, e := range p.Evidence {
				dup := false
				for _, x := range list[i].Evidence {
					dup = dup || x.MessageID == e.MessageID
				}
				if !dup {
					list[i].Evidence = append(list[i].Evidence, e)
				}
			}
			return list
		}
	}
	if p.Evidence == nil {
		p.Evidence = []Evidence{}
	}
	return append(list, p)
}
