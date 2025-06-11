import anthropic
from dotenv import load_dotenv
import os

load_dotenv()

CLAUDE = os.getenv("CLAUDE")


if not CLAUDE:
    raise ValueError("CLAUDE environment variable is required")

client = anthropic.Anthropic(
    # defaults to os.environ.get("ANTHROPIC_API_KEY")
    api_key=CLAUDE,
)

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=20000,
    temperature=1,
    system="you are a industry and academic specialist lecture with 20 year of experience in teaching student ranging between 8 to 30 age",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "create a unversity/school like exam/test question paper for 50 marks using provided informations to help me to master these topic {information : Cancer invasion and metastasis are the major causes of\ncancer patient mortality. Various growth factors, including\nhepatocyte growth factor (HGF), are known to promote cancer\ninvasion and metastasis, but the regulatory mechanisms\ninvolved are not fully understood. Here, we show that HGF-\npromoted migration and invasion of breast cancer cells are\nregulated by CUB domain-containing protein 1 (CDCP1), a\ntransmembrane activator of SRC kinase. In metastatic human\nbreast cancer cell line MDA-MB-231, which highly expresses\nthe HGF receptor MET and CDCP1, we show that CDCP1\nknockdown attenuated HGF-induced MET activation, followed\nby suppression of lamellipodia formation and cell migration/\ninvasion. In contrast, in the low invasive/nonmetastatic breast\ncancer cell line T47D, which had no detectable MET and\nCDCP1 expression, ectopic MET expression stimulated the\nHGF-dependent activation of invasive activity, and concomi-\ntant CDCP1 expression activated SRC and further promoted\ninvasive activity. In these cells, CDCP1 expression dramatically\nactivated HGF-induced membrane remodeling, which was\naccompanied by activation of the small GTPase Rac1. Analysis\nof guanine nucleotide exchange factors revealed that ARH-\nGEF7 was specifically required for CDCP1-dependent induc-\ntion of HGF-induced invasive ability. Furthermore,\nimmunofluorescence staining demonstrated that CDCP1\ncoaccumulated with ARHGEF7. Finally, we confirmed that the\nCDCP1-SRC axis was also crucial for HGF and ARHGEF7-\nRAC1 signaling in MDA-MB-231 cells. Altogether, these re-\nsults demonstrate that the CDCP1-SRC-ARHGEF7-RAC1\npathway plays an important role in the HGF-induced invasion\nof a subset of breast cancer cells.}"
                }
            ]
        }
    ]
)
print(message.content)