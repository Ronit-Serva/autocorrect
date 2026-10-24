// An offline, deterministic spelling corrector. See README.md for the design.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#ifdef __linux__
#include <unistd.h>
#endif

namespace ac {
constexpr size_t MAX_WORD = 64;
constexpr size_t PREFIX = 7;
constexpr char MAGIC[] = "ACIDX003";
constexpr char CONTEXT_MAGIC[] = "ACIDX004";
constexpr char REFINED_MAGIC[] = "ACIDX005";
constexpr char COMPACT_MAGIC[] = "ACIDX006";
constexpr uint32_t NO_WORD = UINT32_MAX;
using std::string;

bool valid(const string& s) {
    if (s.empty()) return false;
    for (unsigned char c : s) if ((c < 'a' || c > 'z') && c != '\'') return false;
    return true;
}
bool vowel(char c) { return c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' || c == 'y'; }
string vowel_signature(const string& s) {
    string out;
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (!vowel(c)) continue;
        if (c == 'e' && i + 1 == s.size() && i > 1 && !vowel(s[i - 1]) && !out.empty()) continue;
        if (i + 1 < s.size()) {
            const string pair = s.substr(i, 2);
            if (pair == "oa" || pair == "au") { c = 'o'; ++i; }
            else if (pair == "ee" || pair == "ie") { c = 'i'; ++i; }
            else if (pair == "oo" || pair == "ou") { c = 'u'; ++i; }
            else if (pair == "ai" || pair == "ay") { c = 'a'; ++i; }
        }
        if (c == 'y') c = 'i';
        if (out.empty() || out.back() != c) out += c;
    }
    return out;
}
uint32_t letter_mask(const string& s) {
    uint32_t mask = 0;
    for (char c : s) mask |= uint32_t{1} << (c == '\'' ? 26 : c - 'a');
    return mask;
}
bool too_many_missing_letters(uint32_t a, uint32_t b, int limit) {
    uint32_t missing = a & ~b;
    for (int count = 0; missing; ++count, missing &= missing - 1)
        if (count >= limit) return true;
    return false;
}
std::vector<uint16_t> bigrams(const string& s) {
    std::vector<uint16_t> out;
    if (s.size() > 1) out.reserve(s.size() - 1);
    for (size_t i = 1; i < s.size(); ++i)
        out.push_back(static_cast<uint16_t>((static_cast<unsigned char>(s[i - 1]) << 8) | static_cast<unsigned char>(s[i])));
    std::sort(out.begin(), out.end());
    return out;
}
double bigram_distance(const std::vector<uint16_t>& a, const std::vector<uint16_t>& b) {
    size_t i = 0, j = 0, common = 0;
    while (i < a.size() && j < b.size()) {
        if (a[i] == b[j]) { ++common; ++i; ++j; }
        else if (a[i] < b[j]) ++i;
        else ++j;
    }
    return a.empty() && b.empty() ? 0. : 1. - 2. * common / (a.size() + b.size());
}
uint64_t hash(const string& s) {
    uint64_t h = 14695981039346656037ULL;
    for (unsigned char c : s) { h ^= c; h *= 1099511628211ULL; }
    return h;
}

// Generate the original key and all distinct one/two-character deletions.
// Hash collisions can only add candidates; edit distances verify each candidate.
std::vector<uint64_t> deletes(const string& s, int radius) {
    std::vector<uint64_t> keys{hash(s)};
    for (size_t i = 0; i < s.size(); ++i) {
        string one = s.substr(0, i) + s.substr(i + 1);
        keys.push_back(hash(one));
        if (radius == 2) for (size_t j = i; j < one.size(); ++j)
            keys.push_back(hash(one.substr(0, j) + one.substr(j + 1)));
    }
    std::sort(keys.begin(), keys.end());
    keys.erase(std::unique(keys.begin(), keys.end()), keys.end());
    return keys;
}

// A deliberately broad, hand-written sound key, not a pronunciation model.
string phonetic(string s, bool refined = false) {
    if (s.size() > 1) {
        string start = s.substr(0, 2);
        if (start == "kn" || start == "gn" || start == "pn" || start == "wr" || start == "ps") s.erase(0, 1);
    }
    string out;
    auto emit = [&](const string& t) {
        for (char c : t) if (out.empty() || out.back() != c) out += c;
    };
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i], next = i + 1 < s.size() ? s[i + 1] : '\0';
        if (c == '\'') continue;
        if (vowel(c)) { if (i == 0) emit(refined ? string(1, static_cast<char>(c - 'a' + 'A')) : "A"); continue; }
        if (c == 'p' && next == 'h') { emit("F"); ++i; }
        else if ((c == 's' || c == 'c') && next == 'h') { emit("X"); ++i; }
        else if (c == 't' && next == 'h') { emit("T"); ++i; }
        else if (c == 'w' && next == 'h') { emit("W"); ++i; }
        else if (c == 'g' && next == 'h' && i > 0 && vowel(s[i - 1])) {
            if (i + 2 == s.size()) emit("F");
            ++i;
        }
        else if (c == 'c') emit(next == 'e' || next == 'i' || next == 'y' ? "S" : "K");
        else if (c == 'g') emit(next == 'e' || next == 'i' || next == 'y' ? "J" : (refined ? "G" : "K"));
        else if (c == 'q' || c == 'k') emit("K");
        else if (c == 'x') emit("KS");
        else if (c == 'z' || c == 's') emit(refined && c == 'z' ? "Z" : "S");
        else if (c == 'v' || c == 'f') emit(refined && c == 'v' ? "V" : "F");
        else if (c == 'd' || c == 't') emit(refined && c == 'd' ? "D" : "T");
        else if (c == 'b' || c == 'p') emit(refined && c == 'b' ? "B" : "P");
        else if (c == 'h') { if (i == 0 || (vowel(next) && !vowel(s[i - 1]))) emit("H"); }
        else emit(string(1, static_cast<char>(c - 'a' + 'A')));
    }
    // Expansions such as x -> KS must stay within the distance matrix bound.
    return out.substr(0, MAX_WORD);
}

// Contextual spelling rewrites before consonant-class encoding. These are
// productive sequences, never complete-word correction mappings.
string contextual_phonetic(string s, bool refined = false) {
    string normalized;
    for (size_t i = 0; i < s.size();) {
        auto at = [&](const string& part) { return s.compare(i, part.size(), part) == 0; };
        if (at("sch")) { normalized += "sk"; i += 3; }
        else if (at("tion") || at("sion") || at("cian")) { normalized += "shn"; i += 4; }
        else if (at("tch")) { normalized += "ch"; i += 3; }
        else if (at("dge") || at("dgi") || at("dgy")) { normalized += "j"; i += 3; }
        else if (at("igh")) { normalized += "i"; i += 3; }
        else if (at("mb") && i + 2 == s.size()) { normalized += "m"; i += 2; }
        else if (at("gn") && i + 2 == s.size()) { normalized += "n"; i += 2; }
        else if (at("chr") || at("chl")) { normalized += "k"; i += 2; }
        else normalized += s[i++];
    }
    return phonetic(normalized, refined);
}

// Optimal string alignment: Levenshtein edits plus adjacent transpositions.
int distance(const string& a, const string& b) {
    int storage[3][MAX_WORD + 1];
    int *prev2 = storage[0], *prev = storage[1], *row = storage[2];
    for (size_t j = 0; j <= b.size(); ++j) prev[j] = static_cast<int>(j);
    for (size_t i = 1; i <= a.size(); ++i) {
        row[0] = static_cast<int>(i);
        for (size_t j = 1; j <= b.size(); ++j) {
            row[j] = std::min({prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1])});
            if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1])
                row[j] = std::min(row[j], prev2[j - 2] + 1);
        }
        std::swap(prev2, prev); std::swap(prev, row);
    }
    return prev[b.size()];
}

// Exact OSA distance inside a band; larger distances are reported as cutoff+1.
// Filtering only needs to distinguish candidates inside the allowed radius.
int bounded_distance(const string& a, const string& b, int cutoff) {
    const int n = static_cast<int>(a.size()), m = static_cast<int>(b.size());
    if (std::abs(n - m) > cutoff) return cutoff + 1;
    const int inf = cutoff + 1;
    int storage[3][MAX_WORD + 1];
    int *prev2 = storage[0], *prev = storage[1], *row = storage[2];
    std::fill(prev, prev + m + 1, inf);
    for (int j = 0; j <= std::min(m, cutoff); ++j) prev[j] = j;
    for (int i = 1; i <= n; ++i) {
        const int start = std::max(1, i - cutoff), end = std::min(m, i + cutoff);
        row[0] = i <= cutoff ? i : inf;
        if (start > 1) row[start - 1] = inf;
        int smallest = row[0];
        for (int j = start; j <= end; ++j) {
            row[j] = std::min({prev[j] + 1, row[j - 1] + 1,
                              prev[j - 1] + (a[i - 1] != b[j - 1])});
            if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1])
                row[j] = std::min(row[j], prev2[j - 2] + 1);
            smallest = std::min(smallest, row[j]);
        }
        if (end < m) row[end + 1] = inf;
        // No future path can return to the band after every prefix is too costly.
        if (smallest > cutoff) return inf;
        std::swap(prev2, prev); std::swap(prev, row);
    }
    return std::min(prev[m], inf);
}

bool keyboard_neighbor(char a, char b) {
    static const std::array<std::pair<float, float>, 26> positions = [] {
        std::array<std::pair<float, float>, 26> p{};
        const string rows[] = {"qwertyuiop", "asdfghjkl", "zxcvbnm"};
        for (int r = 0; r < 3; ++r) for (size_t c = 0; c < rows[r].size(); ++c)
            p[rows[r][c] - 'a'] = {static_cast<float>(c) + 0.25f * r, static_cast<float>(r)};
        return p;
    }();
    if (a < 'a' || a > 'z' || b < 'a' || b > 'z') return false;
    auto p = positions[a - 'a'], q = positions[b - 'a'];
    float dx = p.first - q.first, dy = p.second - q.second;
    return dx * dx + dy * dy <= 1.6f;
}

struct Rule { string a, b; double cost; bool initial = false, final = false; };
using RuleTable = std::array<std::vector<Rule>, 128 * 128>;
const RuleTable& rules(bool extended = false) {
    static const auto build = [](bool extra) {
        RuleTable t;
        // Productive spelling/sound patterns, applied in either direction.
        std::vector<Rule> r = {
            {"ph", "f", .35}, {"ck", "k", .35}, {"qu", "kw", .4},
            {"cqu", "kw", .45}, {"c", "k", .55}, {"c", "s", .6},
            {"g", "j", .6}, {"tion", "shun", .65}, {"sion", "zhun", .7},
            {"ture", "cher", .75}, {"ee", "i", .6}, {"oo", "u", .6},
            {"eau", "o", .65}, {"ai", "ay", .5}, {"ie", "ei", .55},
            {"ight", "ite", .6}, {"dge", "j", .6}, {"tch", "ch", .4}
        };
        if (extra) {
            const std::vector<Rule> added = {
                {"kn", "n", .35, true, false}, {"wr", "r", .35, true, false},
                {"wh", "w", .4, true, false}, {"mb", "m", .35, false, true},
                {"gn", "n", .45, false, true}, {"ght", "t", .5},
                {"ea", "e", .5}, {"ea", "ee", .5}, {"oa", "o", .45},
                {"ai", "a", .5}, {"ou", "u", .55}, {"au", "o", .55},
                {"ey", "y", .4, false, true}, {"ough", "o", .7},
                {"y", "i", .55}, {"ch", "k", .65}, {"sc", "s", .55}
            };
            r.insert(r.end(), added.begin(), added.end());
        }
        for (const auto& x : r) {
            t[static_cast<unsigned char>(x.a.back()) * 128 + static_cast<unsigned char>(x.b.back())].push_back(x);
            t[static_cast<unsigned char>(x.b.back()) * 128 + static_cast<unsigned char>(x.a.back())].push_back({x.b, x.a, x.cost, x.initial, x.final});
        }
        return t;
    };
    static const RuleTable ordinary = build(false), expanded = build(true);
    return extended ? expanded : ordinary;
}

double gap(const string& s, size_t i, bool spelling_costs = false) {
    if (spelling_costs && s[i] == 'e' && i + 1 == s.size()) return .45;
    if (s[i] == '\'') return .35;
    if ((i && s[i] == s[i - 1]) || (i + 1 < s.size() && s[i] == s[i + 1])) return spelling_costs ? .35 : .45;
    return vowel(s[i]) ? .8 : 1.;
}
double weighted_distance(const string& a, const string& b, double transpose_cost = .65, bool spelling_costs = false, bool extended = false, double insertion_scale = 1.) {
    double d[MAX_WORD + 1][MAX_WORD + 1];
    d[0][0] = 0;
    for (size_t i = 1; i <= a.size(); ++i) d[i][0] = d[i - 1][0] + gap(a, i - 1, spelling_costs);
    for (size_t j = 1; j <= b.size(); ++j) d[0][j] = d[0][j - 1] + insertion_scale * gap(b, j - 1, spelling_costs);
    const auto& table = rules(extended);
    for (size_t i = 1; i <= a.size(); ++i) for (size_t j = 1; j <= b.size(); ++j) {
        char x = a[i - 1], y = b[j - 1];
        double sub = x == y ? 0 : (vowel(x) && vowel(y) ? (spelling_costs ? .8 : .55) : (keyboard_neighbor(x, y) ? .8 : 1.));
        d[i][j] = std::min({d[i - 1][j] + gap(a, i - 1, spelling_costs), d[i][j - 1] + insertion_scale * gap(b, j - 1, spelling_costs), d[i - 1][j - 1] + sub});
        if (i > 1 && j > 1 && x == b[j - 2] && a[i - 2] == y)
            d[i][j] = std::min(d[i][j], d[i - 2][j - 2] + transpose_cost);
        for (const auto& r : table[static_cast<unsigned char>(x) * 128 + static_cast<unsigned char>(y)]) {
            if (i >= r.a.size() && j >= r.b.size() &&
                (!r.initial || (i == r.a.size() && j == r.b.size())) &&
                (!r.final || (i == a.size() && j == b.size())) &&
                a.compare(i - r.a.size(), r.a.size(), r.a) == 0 && b.compare(j - r.b.size(), r.b.size(), r.b) == 0)
                d[i][j] = std::min(d[i][j], d[i - r.a.size()][j - r.b.size()] + r.cost);
        }
    }
    return d[a.size()][b.size()];
}

struct Options {
    bool wide = false;
    double known_ratio = 0.;
    bool possessives = false;
    bool extended_rules = true;
    bool spelling_costs = true;
    double suffix_weight = .15;
    double boundary_weight = .25;
    double transpose_cost = .35;
    double edit_weight = .5;
    double sound_weight = .15;
    double prior_weight = .08;
    double insertion_scale = .75;
    double vowel_weight = 0.;
    double ngram_weight = .5;
    bool edge_transpositions = true;
};

Options legacy_options() {
    Options o;
    o.extended_rules = false; o.spelling_costs = false;
    o.suffix_weight = 0; o.boundary_weight = 0;
    o.transpose_cost = .65; o.edit_weight = 0;
    o.sound_weight = .28; o.prior_weight = .12;
    o.insertion_scale = 1.; o.vowel_weight = 0.; o.ngram_weight = 0.;
    o.edge_transpositions = false;
    return o;
}

struct Entry { string word, phone; uint32_t weight; double prior; };
struct Posting {
    uint64_t key;
    uint32_t id;
    bool operator<(const Posting& b) const { return key < b.key || (key == b.key && id < b.id); }
    bool operator==(const Posting& b) const { return key == b.key && id == b.id; }
};

// Explicit little-endian serialization, independent of compiler padding/ABI.
void put(std::ostream& out, uint64_t n, int bytes) {
    for (int i = 0; i < bytes; ++i) { out.put(static_cast<char>(n & 255)); n >>= 8; }
}
uint64_t get(const std::vector<unsigned char>& buf, size_t& at, size_t bytes) {
    if (at > buf.size() || bytes > buf.size() - at) throw std::runtime_error("truncated index; run ./build.sh");
    uint64_t n = 0;
    for (size_t i = 0; i < bytes; ++i) n |= static_cast<uint64_t>(buf[at++]) << (8 * i);
    return n;
}

void build_index(const string& lexicon, const string& path, bool contextual = false, bool refined = false, bool compact = false) {
    std::ifstream in(lexicon);
    if (!in) throw std::runtime_error("cannot open lexicon: " + lexicon);
    std::vector<Entry> words;
    string line;
    while (std::getline(in, line)) {
        std::istringstream row(line);
        string word, extra; uint64_t weight;
        if (!(row >> word >> weight) || row >> extra || !valid(word) || word.size() > MAX_WORD || weight == 0 || weight > UINT32_MAX)
            throw std::runtime_error("invalid dictionary row: " + line);
        words.push_back({word, contextual ? contextual_phonetic(word, refined) : phonetic(word), static_cast<uint32_t>(weight), 0});
    }
    if (words.empty()) throw std::runtime_error("empty dictionary");
    std::sort(words.begin(), words.end(), [](const Entry& a, const Entry& b) {
        return a.weight != b.weight ? a.weight > b.weight : a.word < b.word;
    });
    std::unordered_map<string, bool> unique;
    std::vector<Posting> spelling, sound;
    spelling.reserve(words.size() * 27);
    sound.reserve(words.size() * 8);
    for (uint32_t id = 0; id < words.size(); ++id) {
        const auto& w = words[id];
        if (!unique.emplace(w.word, true).second) throw std::runtime_error("duplicate dictionary entry: " + w.word);
        for (auto key : deletes(w.word.substr(0, PREFIX), 2)) spelling.push_back({key, id});
        for (auto key : deletes(w.phone, 1)) sound.push_back({key, id});
    }
    for (auto* index : {&spelling, &sound}) {
        std::sort(index->begin(), index->end());
        index->erase(std::unique(index->begin(), index->end()), index->end());
    }
    std::ofstream out(path, std::ios::binary);
    if (!out) throw std::runtime_error("cannot write index: " + path);
    out.write(compact ? COMPACT_MAGIC : (refined ? REFINED_MAGIC : (contextual ? CONTEXT_MAGIC : MAGIC)), 8);
    put(out, words.size(), 4); put(out, spelling.size(), 8); put(out, sound.size(), 8);
    for (const auto& w : words) {
        put(out, w.word.size(), 1); put(out, w.weight, 4);
        out.write(w.word.data(), static_cast<std::streamsize>(w.word.size()));
        if (compact) { put(out, w.phone.size(), 1); out.write(w.phone.data(), static_cast<std::streamsize>(w.phone.size())); }
    }
    for (const auto* index : {&spelling, &sound}) {
        if (compact) {
            size_t groups = 0;
            for (size_t i = 0; i < index->size(); ++i) if (i == 0 || (*index)[i].key != (*index)[i - 1].key) ++groups;
            put(out, groups, 8);
            for (size_t i = 0; i < index->size(); ++i) if (i == 0 || (*index)[i].key != (*index)[i - 1].key) {
                put(out, (*index)[i].key, 8); put(out, i, 4);
            }
            for (const auto& p : *index) put(out, p.id, 4);
        } else for (const auto& p : *index) { put(out, p.key, 8); put(out, p.id, 4); }
    }
    if (!out) throw std::runtime_error("failed writing index");
    std::cerr << "Indexed " << words.size() << " words, " << spelling.size() << " spelling and " << sound.size() << " sound postings\n";
}

struct Candidate { uint32_t id; int edits, sound_edits; double cost, score; };
struct Result { string word, reason; std::vector<Candidate> candidates; };

// Store each hash once, followed by offsets into a contiguous word-ID array.
struct PostingIndex {
    std::vector<uint64_t> keys;
    std::vector<uint32_t> offsets, ids;
};

class Corrector {
    Options options;
    bool contextual = false;
    bool refined = false;
    std::vector<Entry> words;
    std::vector<uint32_t> masks;
    std::vector<string> vowel_keys;
    std::vector<std::vector<uint16_t>> word_bigrams;
    // A flat open-addressed table avoids an allocation for every dictionary word.
    std::vector<uint32_t> exact;
    PostingIndex spelling, sound;
    std::vector<uint32_t> seen;
    uint32_t generation = 0;
    std::unordered_map<string, string> cache;
    uint32_t find_exact(const string& word) const {
        size_t slot = hash(word) & (exact.size() - 1);
        while (exact[slot] != NO_WORD) {
            if (words[exact[slot]].word == word) return exact[slot];
            slot = (slot + 1) & (exact.size() - 1);
        }
        return NO_WORD;
    }
public:
    explicit Corrector(const string& path, Options config = {}) : options(config) {
        std::ifstream file(path, std::ios::binary | std::ios::ate);
        if (!file) throw std::runtime_error("cannot open " + path + "; run ./build.sh first");
        auto size = file.tellg();
        if (size < 28 || size > 512 * 1024 * 1024) throw std::runtime_error("invalid index size");
        std::vector<unsigned char> buf(static_cast<size_t>(size));
        file.seekg(0); file.read(reinterpret_cast<char*>(buf.data()), size);
        const string magic(buf.begin(), buf.begin() + 8);
        const bool compact = magic == string(COMPACT_MAGIC, 8);
        if (!file || (!compact && magic != string(MAGIC, 8) && magic != string(CONTEXT_MAGIC, 8) && magic != string(REFINED_MAGIC, 8))) throw std::runtime_error("invalid index header");
        refined = magic == string(REFINED_MAGIC, 8);
        contextual = compact || refined || magic == string(CONTEXT_MAGIC, 8);
        size_t at = 8;
        auto n = get(buf, at, 4), ns = get(buf, at, 8), np = get(buf, at, 8);
        if (n == 0 || n > 1000000 || ns > buf.size() / (compact ? 4 : 12) || np > buf.size() / (compact ? 4 : 12)) throw std::runtime_error("invalid index counts");
        words.reserve(n); masks.reserve(n);
        if (options.vowel_weight > 0) vowel_keys.reserve(n);
        if (options.ngram_weight > 0) word_bigrams.reserve(n);
        size_t slots = 1;
        while (slots < n * 2) slots *= 2;
        exact.assign(slots, NO_WORD);
        for (uint32_t i = 0; i < n; ++i) {
            size_t len = get(buf, at, 1); auto weight = get(buf, at, 4);
            if (len == 0 || len > MAX_WORD || len > buf.size() - at || weight == 0) throw std::runtime_error("invalid index entry");
            string word(buf.begin() + at, buf.begin() + at + len); at += len;
            if (!valid(word) || find_exact(word) != NO_WORD) throw std::runtime_error("invalid or duplicate index word");
            string phone;
            if (compact) {
                size_t phone_len = get(buf, at, 1);
                if (phone_len > MAX_WORD || phone_len > buf.size() - at) throw std::runtime_error("invalid sound-key length");
                phone.assign(buf.begin() + at, buf.begin() + at + phone_len); at += phone_len;
                for (char c : phone) if (c < 'A' || c > 'Z') throw std::runtime_error("invalid sound key");
            } else phone = contextual ? contextual_phonetic(word, refined) : phonetic(word);
            words.push_back({word, phone, static_cast<uint32_t>(weight), std::log1p(static_cast<double>(weight))});
            masks.push_back(letter_mask(word));
            if (options.vowel_weight > 0) vowel_keys.push_back(vowel_signature(word));
            if (options.ngram_weight > 0) word_bigrams.push_back(bigrams(word));
            size_t slot = hash(word) & (exact.size() - 1);
            while (exact[slot] != NO_WORD) slot = (slot + 1) & (exact.size() - 1);
            exact[slot] = i;
        }
        if (!compact && (ns + np != (buf.size() - at) / 12 || (buf.size() - at) % 12)) throw std::runtime_error("invalid index length");
        auto load = [&](PostingIndex& index, size_t count) {
            index.ids.reserve(count);
            if (compact) {
                const size_t groups = get(buf, at, 8);
                if (groups > count || groups > (buf.size() - at) / 12) throw std::runtime_error("invalid key count");
                index.keys.reserve(groups); index.offsets.reserve(groups + 1);
                for (size_t i = 0; i < groups; ++i) {
                    auto key = get(buf, at, 8), offset = get(buf, at, 4);
                    if (offset >= count || (i == 0 && offset != 0) ||
                        (i && (key <= index.keys.back() || offset <= index.offsets.back()))) throw std::runtime_error("invalid key ordering");
                    index.keys.push_back(key); index.offsets.push_back(static_cast<uint32_t>(offset));
                }
                if ((count != 0 && groups == 0) || count > (buf.size() - at) / 4) throw std::runtime_error("invalid posting count");
                size_t group = 0;
                for (size_t i = 0; i < count; ++i) {
                    const auto id = get(buf, at, 4);
                    if (group + 1 < groups && i == index.offsets[group + 1]) ++group;
                    if (id >= n || (i > index.offsets[group] && id <= index.ids.back())) throw std::runtime_error("invalid posting id or ordering");
                    index.ids.push_back(static_cast<uint32_t>(id));
                }
            } else {
                Posting last{};
                for (size_t i = 0; i < count; ++i) {
                    const Posting p{get(buf, at, 8), static_cast<uint32_t>(get(buf, at, 4))};
                    if (p.id >= n || (i && p < last)) throw std::runtime_error("invalid posting id or ordering");
                    if (i == 0 || p.key != last.key) { index.keys.push_back(p.key); index.offsets.push_back(static_cast<uint32_t>(i)); }
                    index.ids.push_back(p.id); last = p;
                }
            }
            index.offsets.push_back(static_cast<uint32_t>(count));
        };
        load(spelling, ns); load(sound, np);
        if (at != buf.size()) throw std::runtime_error("invalid index length");
        seen.resize(n); cache.reserve(16384);
    }

    Result analyze(const string& input, bool exhaustive = true) {
        auto known = find_exact(input);
        if (known != NO_WORD && options.known_ratio == 0.) return {input, "dictionary word: preserved", {}};
        if (!valid(input) || input.size() > MAX_WORD || input.size() < 3)
            return {input, "outside conservative correction range: preserved", {}};
        if (options.possessives && input.size() > 3 && input.compare(input.size() - 2, 2, "'s") == 0) {
            const string stem = input.substr(0, input.size() - 2);
            if (stem.find('\'') == string::npos) {
                auto result = analyze(stem, exhaustive);
                if (find_exact(result.word) != NO_WORD) {
                    result.word += "'s";
                    result.reason = "possessive stem correction";
                    return result;
                }
            }
        }
        if (++generation == 0) { std::fill(seen.begin(), seen.end(), 0); ++generation; }
        std::vector<uint32_t> ids;
        auto collect = [&](const PostingIndex& index, const std::vector<uint64_t>& keys, size_t limit) {
            for (auto key : keys) {
                auto it = std::lower_bound(index.keys.begin(), index.keys.end(), key);
                if (it == index.keys.end() || *it != key) continue;
                const size_t group = static_cast<size_t>(it - index.keys.begin());
                const size_t begin = index.offsets[group], end = std::min<size_t>(index.offsets[group + 1], begin + std::min(limit, index.ids.size()));
                for (size_t i = begin; i < end; ++i) {
                    const auto id = index.ids[i];
                    if (seen[id] != generation) { seen[id] = generation; ids.push_back(id); }
                }
            }
        };
        collect(spelling, deletes(input.substr(0, PREFIX), 2), std::numeric_limits<size_t>::max());
        string phone = contextual ? contextual_phonetic(input, refined) : phonetic(input);
        // Frequency-sorted posting IDs bound very broad phonetic buckets.
        collect(sound, {hash(phone)}, 256);
        if (input.size() >= 5) collect(sound, deletes(phone, 1), 128);
        if (options.wide && input.size() >= 6) collect(sound, deletes(phone, 2), 64);
        std::vector<Candidate> candidates;
        const uint32_t input_mask = letter_mask(input);
        const string input_vowels = options.vowel_weight > 0 ? vowel_signature(input) : "";
        const auto input_bigrams = options.ngram_weight > 0 ? bigrams(input) : std::vector<uint16_t>{};
        if (!exhaustive) candidates.reserve(3);
        auto better = [&](const Candidate& a, const Candidate& b) {
            if (a.score != b.score) return a.score < b.score;
            if (words[a.id].weight != words[b.id].weight) return words[a.id].weight > words[b.id].weight;
            return words[a.id].word < words[b.id].word;
        };
        for (auto id : ids) {
            const auto& w = words[id];
            if (std::abs(static_cast<int>(input.size()) - static_cast<int>(w.word.size())) > 4) continue;
            const int limit = options.wide ? std::min(6, std::max(3, static_cast<int>(input.size()) / 2 + 1))
                                          : std::min(5, std::max(2, static_cast<int>(input.size()) / 2));
            const int raw_limit = input.size() <= 3 ? 1 : limit;
            if (too_many_missing_letters(input_mask, masks[id], raw_limit) ||
                too_many_missing_letters(masks[id], input_mask, raw_limit)) continue;
            int raw = bounded_distance(input, w.word, input.size() <= 3 ? 1 : limit);
            if (raw > limit) continue;
            if (input.size() <= 3 && raw > 1) continue;
            int pd = raw > 2 ? bounded_distance(phone, w.phone, options.wide ? 2 : 1)
                             : distance(phone, w.phone);
            if (raw > 2 && (pd > (options.wide ? 2 : 1) || raw > limit)) continue;
            const double vowel_score = options.vowel_weight > 0 ? options.vowel_weight * distance(input_vowels, vowel_keys[id]) : 0.;
            const double ngram_score = options.ngram_weight > 0 ? options.ngram_weight * bigram_distance(input_bigrams, word_bigrams[id]) : 0.;
            bool first_different = input.front() != w.word.front(), last_different = input.back() != w.word.back();
            if (options.edge_transpositions && w.word.size() > 1) {
                if (input[0] == w.word[1] && input[1] == w.word[0]) first_different = false;
                if (input.back() == w.word[w.word.size() - 2] && input[input.size() - 2] == w.word.back()) last_different = false;
            }
            double fixed_score = options.edit_weight * raw
                + options.sound_weight * pd - (known != NO_WORD ? .2 : options.prior_weight) * w.prior
                + options.boundary_weight * first_different
                + options.suffix_weight * last_different + vowel_score + ngram_score;
            // Weighted cost is nonnegative. Once its lower bound cannot enter
            // the best two, it cannot change the winner or confidence margin.
            if (!exhaustive && candidates.size() == 2 && fixed_score > candidates[1].score + 1e-12) continue;
            double cost = weighted_distance(input, w.word, options.transpose_cost, options.spelling_costs, options.extended_rules, options.insertion_scale);
            double score = (1 - options.edit_weight) * cost + options.edit_weight * raw
                + options.sound_weight * pd - (known != NO_WORD ? .2 : options.prior_weight) * w.prior
                + options.boundary_weight * first_different
                + options.suffix_weight * last_different + vowel_score + ngram_score;
            candidates.push_back({id, raw, pd, cost, score});
            if (!exhaustive) {
                std::sort(candidates.begin(), candidates.end(), better);
                if (candidates.size() > 2) candidates.pop_back();
            }
        }
        if (exhaustive) std::sort(candidates.begin(), candidates.end(), better);
        Result result{input, "no confident candidate: preserved", std::move(candidates)};
        if (result.candidates.empty()) return result;
        const auto& best = result.candidates[0];
        double ceiling = std::min(3.2, 1.05 + .2 * input.size());
        double margin = result.candidates.size() > 1 ? result.candidates[1].score - best.score : 100.;
        if (known != NO_WORD && best.id != known) {
            const auto& original = words[known];
            if (best.edits > 1 || best.cost > 1. ||
                words[best.id].weight < options.known_ratio * original.weight ||
                best.score + .15 >= -.2 * original.prior) return result;
        }
        if (best.cost <= ceiling && (best.edits <= 2 || margin >= .12)) {
            result.word = words[best.id].word;
            result.reason = "best edit/sound/count candidate";
        }
        return result;
    }
    string correct(const string& input) {
        auto it = cache.find(input);
        if (it != cache.end()) return it->second;
        auto result = analyze(input, false);
        // Fixed cache cap prevents input stream length from growing memory forever.
        if (cache.size() < 50000 && input.size() <= MAX_WORD) cache.emplace(input, result.word);
        return result.word;
    }
    void trace(const string& input) {
        const auto r = analyze(input);
        std::cout << input << '\t' << r.word << '\t' << r.reason << "\n";
        for (const auto& c : r.candidates) {
            const auto& w = words[c.id];
            std::cout << "\t" << w.word << '\t' << c.edits << '\t' << c.sound_edits
                      << '\t' << c.cost << '\t' << w.weight << '\t' << c.score << '\n';
        }
    }
    void explain(const string& input) {
        auto r = analyze(input);
        std::cout << input << " -> " << r.word << "\n" << r.reason << "\n";
        std::cout << "candidate\tedits\tsound_edits\tweighted_cost\tcount_weight\tscore (lower is better)\n";
        for (size_t i = 0; i < std::min<size_t>(10, r.candidates.size()); ++i) {
            const auto& c = r.candidates[i]; const auto& w = words[c.id];
            std::cout << w.word << '\t' << c.edits << '\t' << c.sound_edits << '\t' << c.cost << '\t' << w.weight << '\t' << c.score << '\n';
        }
    }
};

std::filesystem::path executable_dir(const char* argv0) {
#ifdef __linux__
    std::array<char, 8192> path{};
    auto n = readlink("/proc/self/exe", path.data(), path.size() - 1);
    if (n > 0) return std::filesystem::path(string(path.data(), static_cast<size_t>(n))).parent_path();
#elif defined(__APPLE__)
    uint32_t size = 0;
    _NSGetExecutablePath(nullptr, &size);
    std::vector<char> path(size);
    if (_NSGetExecutablePath(path.data(), &size) == 0) return std::filesystem::weakly_canonical(path.data()).parent_path();
#endif
    return std::filesystem::absolute(argv0).parent_path();
}
} // namespace ac

int main(int argc, char** argv) {
    try {
        std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
        if (argc == 4 && (ac::string(argv[1]) == "--build-index" || ac::string(argv[1]) == "--build-index-enhanced" || ac::string(argv[1]) == "--build-index-refined" || ac::string(argv[1]) == "--build-index-compact")) {
            ac::build_index(argv[2], argv[3], ac::string(argv[1]) != "--build-index", ac::string(argv[1]) == "--build-index-refined", ac::string(argv[1]) == "--build-index-compact"); return 0;
        }
        ac::string index = (ac::executable_dir(argv[0]) / "data/index.bin").string();
        ac::string explain;
        ac::Options options;
        bool trace = false;
        for (int i = 1; i < argc; ++i) {
            ac::string arg = argv[i];
            if (arg == "--index" && i + 1 < argc) index = argv[++i];
            else if (arg == "--explain" && i + 1 < argc) explain = argv[++i];
            else if ((arg == "--edit-weight" || arg == "--sound-weight" || arg == "--prior-weight" || arg == "--transpose-cost" || arg == "--boundary-weight" || arg == "--suffix-weight" || arg == "--insertion-scale" || arg == "--vowel-weight" || arg == "--ngram-weight") && i + 1 < argc) {
                const ac::string value = argv[++i];
                size_t used = 0;
                double number = std::stod(value, &used);
                if (used != value.size() || !std::isfinite(number) || number < 0 || number > 1)
                    throw std::runtime_error("weight must be a number in [0,1]");
                if (arg == "--suffix-weight") options.suffix_weight = number;
                if (arg == "--insertion-scale") options.insertion_scale = number;
                if (arg == "--vowel-weight") options.vowel_weight = number;
                if (arg == "--ngram-weight") options.ngram_weight = number;
                if (arg == "--boundary-weight") options.boundary_weight = number;
                if (arg == "--transpose-cost") options.transpose_cost = number;
                if (arg == "--edit-weight") options.edit_weight = number;
                if (arg == "--sound-weight") options.sound_weight = number;
                if (arg == "--prior-weight") options.prior_weight = number;
            }
            else if (arg == "--profile" && i + 1 < argc) {
                const ac::string profile = argv[++i];
                if (profile == "legacy") options = ac::legacy_options();
                else if (profile == "default") options = ac::Options{};
                else throw std::runtime_error("profile must be default or legacy");
            }
            else if (arg == "--no-spelling-costs") options.spelling_costs = false;
            else if (arg == "--no-extended-rules") options.extended_rules = false;
            else if (arg == "--known-ratio" && i + 1 < argc) {
                const ac::string value = argv[++i]; size_t used = 0;
                options.known_ratio = std::stod(value, &used);
                if (used != value.size() || !std::isfinite(options.known_ratio) || options.known_ratio < 0)
                    throw std::runtime_error("known ratio must be finite and nonnegative");
            }
            else if (arg == "--wide") options.wide = true;
            else if (arg == "--edge-transpositions") options.edge_transpositions = true;
            else if (arg == "--no-edge-transpositions") options.edge_transpositions = false;
            else if (arg == "--possessives") options.possessives = true;
            else if (arg == "--extended-rules") options.extended_rules = true;
            else if (arg == "--spelling-costs") options.spelling_costs = true;
            else if (arg == "--trace") trace = true;
            else if (arg == "--help") {
                std::cout << "Usage: autocorrect [OPTIONS] < input.txt > output.txt\n"
                             "       autocorrect [OPTIONS] --explain WORD\n"
                             "       autocorrect [OPTIONS] --trace < input.txt\n"
                             "       autocorrect --build-index words.tsv index.bin\n"
                             "       autocorrect --build-index-enhanced words.tsv index.bin\n"
                             "       autocorrect --build-index-refined words.tsv index.bin\n"
                             "       autocorrect --build-index-compact words.tsv index.bin\n"
                             "Options: --index PATH, --profile default|legacy\n"
                             "         --edit-weight N --sound-weight N --prior-weight N\n"
                             "         --boundary-weight N --suffix-weight N --transpose-cost N\n"
                             "         --insertion-scale N --vowel-weight N\n"
                             "         --ngram-weight N --edge-transpositions --no-edge-transpositions\n"
                             "         --spelling-costs --no-spelling-costs\n"
                             "         --extended-rules --no-extended-rules\n"
                             "         --known-ratio N --possessives --wide\n"
                             "Weights are in [0,1]. Profiles reset weights; put overrides after them.\n"
                             "Index headers select the matching encoder automatically.\n";
                return 0;
            } else throw std::runtime_error("unknown/incomplete option: " + arg);
        }
        ac::Corrector corrector(index, options);
        if (!explain.empty()) { corrector.explain(explain); return 0; }
        ac::string line;
        while (std::getline(std::cin, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (trace) corrector.trace(line);
            else std::cout << corrector.correct(line) << '\n';
        }
        if (std::cin.bad()) throw std::runtime_error("input read failed");
        std::cout.flush();
        if (!std::cout) throw std::runtime_error("output write failed");
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "autocorrect: " << e.what() << '\n'; return 1;
    }
}
