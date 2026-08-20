package example;
class ParentConverter {
  Object convert(Parent parent, Builder ceb) {
    ceb.alias("example.Parent");
    if (parent.first() != null) {
      String refKey = convertFirst(parent.first());
      ceb.referenceField("first", refKey);
    }
    if (parent.second() != null) {
      String refKey = convertSecond(parent.second());
      ceb.referenceField("second", refKey);
    }
    return null;
  }
  String convertFirst(Child child) { return "First_" + child.id(); }
  String convertSecond(Child child) { return "Second_" + child.id(); }
}
